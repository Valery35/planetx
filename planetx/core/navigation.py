# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Навигация: захват Земли, колесо, наклон и поворот, инерция.

Положение камеры задаётся позой, как в Google Earth. Поза - это точка
взгляда на эллипсоиде (широта, долгота), расстояние до неё, азимут
и наклон. Камера строится из позы функцией Camera.set_look_at. Крен
нулевой по построению: правая ось камеры перпендикулярна нормали
эллипсоида в точке взгляда.

- Захват подбирает широту и долготу точки взгляда методом Ньютона, пока
  схваченная точка не встанет под курсор. Азимут, наклон и расстояние
  не меняются.
- Колесо меняет расстояние, потом точка под курсором ставится на место
  тем же подбором.
- Наклон и поворот меняют только свои величины. Точка взгляда остаётся
  в центре окна.
- Инерция продолжает захват с затухающей скоростью по широте и долготе.
  Поза считается от позы в момент отпускания как функция времени,
  поэтому путь не зависит от частоты кадров.

Время передаётся явно, в секундах. Модуль Qt не знает.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .camera import orientation
    from .ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,
                            ray_intersect, surface_normal)
except ImportError:  # headless-тесты
    from camera import orientation
    from ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,
                           ray_intersect, surface_normal)

MIN_ALTITUDE = 50.0
MAX_ALTITUDE = 5.0e7
MAX_TILT = 85.0
MAX_LAT = 89.99
INERTIA_TAU = 0.35  # постоянная затухания, секунды
VELOCITY_WINDOW = 0.08  # по скольким последним секундам мерится скорость
STILL_BEFORE_RELEASE = 0.06  # пауза, которая гасит инерцию
INERTIA_STOP = 0.002  # остаток пути, после которого инерция стоит
ZOOM_TAU = 0.1
PIN_TOLERANCE = 1e-3  # пикселей
PIN_FAIL = 0.5


class Pose:
    """Точка взгляда, расстояние, азимут и наклон в градусах."""

    __slots__ = ("lat", "lon", "distance", "heading", "tilt")

    def __init__(self, lat, lon, distance, heading=0.0, tilt=0.0):
        self.lat = lat
        self.lon = lon
        self.distance = distance
        self.heading = heading
        self.tilt = tilt

    def copy(self):
        return Pose(self.lat, self.lon, self.distance, self.heading,
                    self.tilt)

    def eye_rotation(self):
        rot = orientation(self.lat, self.lon, self.heading, self.tilt)
        eye = geodetic_to_ecef(self.lat, self.lon) + rot[:, 2] \
            * self.distance
        return eye, rot

    def apply(self, camera):
        camera.eye, camera.rotation = self.eye_rotation()

    def moved_to(self, lat, lon):
        out = self.copy()
        out.lat = min(MAX_LAT, max(-MAX_LAT, lat))
        out.lon = (lon + 180.0) % 360.0 - 180.0
        return out


def roll(camera, pose):
    """Крен, синус угла правой оси с нормалью в точке взгляда."""
    return float(camera.rotation[:, 0] @ surface_normal(pose.lat,
                                                         pose.lon))


def altitude(eye):
    return float(ecef_to_geodetic(eye)[2])


def focal(camera):
    return camera.height / (2.0 * math.tan(math.radians(camera.fov_y) / 2))


def pixel_at(camera, eye, rot, point):
    """Пиксель точки при положении eye, rot. None, если точка позади."""
    cam = rot.T @ (point - eye)
    if cam[2] >= 0.0:
        return None
    f = focal(camera)
    return np.array([camera.width / 2.0 + f * cam[0] / -cam[2],
                     camera.height / 2.0 - f * cam[1] / -cam[2]])


def ground_under(camera, px, py):
    """Точка эллипсоида под пикселем или None."""
    origin, d = camera.ray(px, py)
    t = ray_intersect(origin, d)
    return None if t is None else origin + d * t


def first_guess(camera, pose, point, px, py):
    """Начальная поза для подбора.

    Под пикселем (px, py) при текущей позе лежит точка Q. Поворот вокруг
    центра Земли, который переводит Q в point, переводит и точку взгляда
    почти туда, где point встанет под пиксель. Для сферы это точно, для
    эллипсоида приближённо. Без такого начала подбор у края диска уходит
    в чужую долину невязки. Если под пикселем нет Земли, начало -
    текущая поза.
    """
    pose.apply(camera)
    q = ground_under(camera, px, py)
    if q is None:
        return pose
    a = q / np.linalg.norm(q)
    b = point / np.linalg.norm(point)
    axis = np.cross(a, b)
    sin = float(np.linalg.norm(axis))
    if sin < 1e-15:
        return pose
    angle = math.atan2(sin, float(a @ b))
    axis /= sin
    look = geodetic_to_ecef(pose.lat, pose.lon)
    # Поворот вектора вокруг оси, формула Родрига.
    turned = (look * math.cos(angle) + np.cross(axis, look) * math.sin(angle)
              + axis * (axis @ look) * (1.0 - math.cos(angle)))
    lat, lon, _ = ecef_to_geodetic(turned)
    return pose.moved_to(float(lat), float(lon))


def solve_pin(camera, pose, point, px, py):
    """Поза с той же дальностью и углами, где point стоит в (px, py).

    Возвращает новую позу или None, если решения нет.
    """
    target = np.array([px, py], dtype=np.float64)
    eye, _ = pose.eye_rotation()
    dist = float(np.linalg.norm(point - eye))
    # Сдвиг точки взгляда на h радиан сдвигает картинку примерно
    # на A·h·f/dist пикселей. Шаг производной - сотая доля пикселя.
    h = math.degrees(0.01 * dist / (6378137.0 * focal(camera)))
    current = first_guess(camera, pose, point, px, py)
    p = pixel_at(camera, *current.eye_rotation(), point)
    if p is None:
        return None
    error = float(np.linalg.norm(p - target))
    for _ in range(30):
        if error < PIN_TOLERANCE:
            return current
        jac = np.empty((2, 2))
        for i, (dlat, dlon) in enumerate(((h, 0.0), (0.0, h))):
            probe = current.moved_to(current.lat + dlat, current.lon + dlon)
            q = pixel_at(camera, *probe.eye_rotation(), point)
            if q is None:
                return None
            jac[:, i] = (q - p) / h
        try:
            delta = np.linalg.solve(jac, target - p)
        except np.linalg.LinAlgError:
            return None
        # Шаг ограничен 20 градусами, чтобы не перепрыгнуть шар.
        biggest = float(np.abs(delta).max())
        if biggest > 20.0:
            delta *= 20.0 / biggest
        # У края диска картинка почти не двигается, и полный шаг Ньютона
        # перелетает. Шаг принимается, только если невязка убывает.
        for _ in range(20):
            trial = current.moved_to(current.lat + delta[0],
                                     current.lon + delta[1])
            q = pixel_at(camera, *trial.eye_rotation(), point)
            if q is not None and np.linalg.norm(q - target) < error:
                break
            delta *= 0.5
        else:
            break
        current, p = trial, q
        error = float(np.linalg.norm(p - target))
    if error > PIN_FAIL:
        return None
    return current


def clamp_distance(pose, distance):
    """Ближайшее к distance расстояние, при котором высота глаза в рамках.
    """
    trial = pose.copy()

    def height(d):
        trial.distance = d
        return altitude(trial.eye_rotation()[0])

    h = height(distance)
    if MIN_ALTITUDE <= h <= MAX_ALTITUDE:
        return distance
    # Высота растёт с расстоянием. Делением пополам между текущим
    # расстоянием и желаемым находится расстояние на границе.
    inside, outside = pose.distance, distance
    for _ in range(60):
        mid = 0.5 * (inside + outside)
        if MIN_ALTITUDE <= height(mid) <= MAX_ALTITUDE:
            inside = mid
        else:
            outside = mid
    return inside


def zoom(camera, pose, px, py, factor):
    """Приблизить в factor раз к точке под курсором.

    factor меньше 1 приближает. Возвращает новую позу или None, если
    под курсором нет Земли.
    """
    point = ground_under(camera, px, py)
    if point is None:
        return None
    scaled = pose.copy()
    scaled.distance = clamp_distance(pose, pose.distance * factor)
    return solve_pin(camera, scaled, point, px, py)


def orbit(pose, d_heading, d_tilt):
    """Повернуть на d_heading и наклонить на d_tilt градусов.

    Наклон ограничен MAX_TILT. Наклон, при котором глаз опускается ниже
    MIN_ALTITUDE, уменьшается до допустимого.
    """
    out = pose.copy()
    out.heading = (pose.heading + d_heading) % 360.0
    wanted = min(MAX_TILT, max(0.0, pose.tilt + d_tilt))
    out.tilt = wanted
    if altitude(out.eye_rotation()[0]) < MIN_ALTITUDE:
        low, high = min(pose.tilt, wanted), max(pose.tilt, wanted)
        for _ in range(50):
            out.tilt = 0.5 * (low + high)
            if altitude(out.eye_rotation()[0]) < MIN_ALTITUDE:
                high = out.tilt
            else:
                low = out.tilt
        out.tilt = low
    return out


class Navigator:
    """Состояние навигации между событиями мыши."""

    def __init__(self, camera, pose):
        self.camera = camera
        self.pose = pose
        pose.apply(camera)
        self.grab = None
        self.history = []
        self.inertia = None
        self.zooming = None
        self.flight = None

    def set_pose(self, pose):
        self.pose = pose
        pose.apply(self.camera)

    # Захват

    def press(self, px, py, now):
        self.stop()
        self.grab = ground_under(self.camera, px, py)
        self.history = [(now, self.pose.lat, self.pose.lon)]
        return self.grab is not None

    def drag(self, px, py, now):
        if self.grab is None:
            return False
        pose = solve_pin(self.camera, self.pose, self.grab, px, py)
        if pose is None:
            return False
        self.set_pose(pose)
        self.history.append((now, pose.lat, pose.lon))
        cutoff = now - 4 * VELOCITY_WINDOW
        self.history = [h for h in self.history if h[0] >= cutoff]
        return True

    def release(self, now):
        """Отпускание. Возвращает True, если началась инерция."""
        history, self.history = self.history, []
        grabbed, self.grab = self.grab, None
        if grabbed is None or len(history) < 2:
            return False
        if now - history[-1][0] > STILL_BEFORE_RELEASE:
            return False
        recent = [h for h in history if h[0] >= now - VELOCITY_WINDOW]
        first = history[max(0, len(history) - len(recent) - 1)]
        last = history[-1]
        span = last[0] - first[0]
        if span <= 0.0:
            return False
        v_lat = (last[1] - first[1]) / span
        d_lon = (last[2] - first[2] + 180.0) % 360.0 - 180.0
        v_lon = d_lon / span
        if v_lat == 0.0 and v_lon == 0.0:
            return False
        self.inertia = (now, self.pose.copy(), v_lat, v_lon)
        return True

    # Колесо

    def wheel(self, px, py, factor, now):
        """Плавное приближение: множитель копится и отдаётся по кадрам."""
        self.inertia = None
        self.flight = None
        log_left = math.log(factor)
        if self.zooming is not None and self.zooming[:2] == (px, py):
            log_left += self.zooming[2]
        self.zooming = (px, py, log_left, now)

    # Наклон и поворот

    def turn(self, d_heading, d_tilt):
        """Поворот гасит инерцию и перелёт, но не обрывает приближение."""
        self.stop_inertia()
        self.flight = None
        self.set_pose(orbit(self.pose, d_heading, d_tilt))

    # Перелёт

    def start_flight(self, flight, now):
        """Начать перелёт, объект из core/flight.py. Всё прочее гасится."""
        self.stop()
        self.flight = (now, flight)

    def stop_inertia(self):
        self.inertia = None

    # Кадр

    def step(self, now):
        """Продвинуть инерцию и плавное приближение. True - ещё идёт."""
        busy = False
        if self.flight is not None:
            start, flight = self.flight
            self.set_pose(flight.pose_at(now - start))
            if now - start >= flight.duration:
                self.flight = None
            else:
                busy = True
        if self.inertia is not None:
            busy = self._step_inertia(now) or busy
        if self.zooming is not None:
            busy = self._step_zoom(now) or busy
        return busy

    def _step_inertia(self, now):
        start, pose, v_lat, v_lon = self.inertia
        remaining = math.exp(-(now - start) / INERTIA_TAU)
        done = remaining < INERTIA_STOP
        if done:
            # Конец пути - его предел. Он один при любой частоте кадров,
            # скачок к нему не больше INERTIA_STOP от всего пути.
            remaining = 0.0
        path = INERTIA_TAU * (1.0 - remaining)
        self.set_pose(pose.moved_to(pose.lat + v_lat * path,
                                    pose.lon + v_lon * path))
        if done:
            self.inertia = None
            return False
        return True

    def _step_zoom(self, now):
        px, py, log_left, last = self.zooming
        dt = max(0.0, now - last)
        part = log_left * (1.0 - math.exp(-dt / ZOOM_TAU))
        if abs(log_left) < 1e-3:
            part = log_left
        pose = zoom(self.camera, self.pose, px, py, math.exp(part))
        log_left -= part
        if pose is not None:
            self.set_pose(pose)
        if pose is None or abs(log_left) < 1e-9:
            self.zooming = None
            return False
        self.zooming = (px, py, log_left, now)
        return True

    def stop(self):
        self.inertia = None
        self.zooming = None
        self.flight = None
