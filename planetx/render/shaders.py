# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тексты шейдеров GLSL 330.

Вершина тайла приходит смещением от центра тайла в float32. Матрица
u_mvp уже включает сдвиг «центр тайла - глаз», посчитанный в float64.
"""

A_KM = 6378.137
SHELL_KM = 300.0  # толщина оболочки атмосферы
SHELL = 1.0 + SHELL_KM / A_KM  # оболочка в долях полуосей эллипсоида

# Воздух на луче из глаза. Плотность падает с высотой по экспоненте,
# рассеяние по каналам как у рэлеевского на уровне моря. Солнца нет,
# свет рассеивается одинаково во все стороны. Луч идёт в координатах
# в долях полуосей, эллипсоид там - единичная сфера. Члены |eye|² - r²
# считаются на процессоре в double, как в счётчике дыр.
#
# Интеграл плотности берётся по двум половинам отрезка от точки,
# ближайшей к центру Земли. Шаги сгущаются к ней как u², там
# плотность наибольшая. Луч по касательной к поверхности из космоса
# проходит около 3900 км, а плотность меняется на 800 км, первый шаг
# около 8 км.
ATMOSPHERE = """
uniform mat3 u_rotation;   // оси камеры в ECEF, по столбцам
uniform vec2 u_tan;        // tan(fov/2)·aspect и tan(fov/2)
uniform vec2 u_viewport;   // размер кадра в пикселях
uniform vec3 u_eye;        // глаз в долях полуосей
uniform vec3 u_axes;       // 1 / полуоси
uniform float u_qc_shell;  // |eye|² - SHELL², посчитано в double
uniform float u_air;       // 1 - атмосфера включена, 0 - выключена
const float RADIUS_KM = %(a_km)r;
// Высота однородной атмосферы вшестеро больше настоящей, иначе гало
// из космоса уже 5 пикселей. Рассеяние уменьшено в той же доле, отвесный столб
// воздуха такой же, как у настоящей атмосферы.
const float SCALE_KM = 50.0;
const vec3 BETA = vec3(0.0058, 0.0135, 0.0331) * 8.0 / SCALE_KM;
const int STEPS = 8;  // шагов на половину отрезка

// Луч через центр пикселя, в метрах на единицу параметра t.
// Составляющая вдоль взгляда равна 1, поэтому t совпадает с глубиной
// пикселя, то есть с w после проекции.
vec3 view_dir() {
    vec2 ndc = gl_FragCoord.xy / u_viewport * 2.0 - 1.0;
    return u_rotation * vec3(ndc.x * u_tan.x, ndc.y * u_tan.y, -1.0);
}

// Интеграл плотности от tc до b в километрах воздуха уровня моря.
float half_depth(vec3 d, float tc, float b, float km_per_t) {
    float span = b - tc;
    float sum = 0.0;
    for (int i = 0; i < STEPS; ++i) {
        float u = (float(i) + 0.5) / float(STEPS);
        vec3 p = u_eye + (tc + span * u * u) * d;
        float h = max(length(p) - 1.0, 0.0) * RADIUS_KM;
        sum += exp(-h / SCALE_KM) * u;
    }
    return sum * 2.0 * abs(span) / float(STEPS) * km_per_t;
}

// Свет воздуха на отрезке луча от глаза до t_end и доля света,
// прошедшая насквозь, в pass.
vec3 air(vec3 dir, float t_end, out vec3 pass) {
    pass = vec3(1.0);
    if (u_air == 0.0) {
        return vec3(0.0);
    }
    vec3 d = dir * u_axes;
    float qa = dot(d, d);
    float qb = dot(u_eye, d);
    float disc = qb * qb - qa * u_qc_shell;
    if (disc <= 0.0) {
        return vec3(0.0);
    }
    float root = sqrt(disc);
    float t0 = max((-qb - root) / qa, 0.0);
    float t1 = min((-qb + root) / qa, t_end);
    if (t1 <= t0) {
        return vec3(0.0);
    }
    float tc = clamp(-qb / qa, t0, t1);
    float km_per_t = length(dir) / 1000.0;
    float depth = half_depth(d, tc, t0, km_per_t)
        + half_depth(d, tc, t1, km_per_t);
    pass = exp(-BETA * depth);
    return 1.0 - pass;
}
""" % {"a_km": A_KM}

TILE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in float a_shade;
uniform mat4 u_mvp;
out vec2 v_uv;
out float v_shade;
out float v_depth;
void main() {
    v_uv = a_uv;
    v_shade = a_shade;
    gl_Position = u_mvp * vec4(a_position, 1.0);
    v_depth = gl_Position.w;
}
"""

SKY_FRAGMENT = """#version 330 core
// Небо и гало: пиксели, где не нарисован ни один тайл. Луч кончается
// на эллипсоиде, если попадает в него.
uniform float u_qc;        // |eye|² - 1, посчитано в double
out vec4 frag_color;
const float SKY_EXPOSURE = 3.5;
""" + ATMOSPHERE + """
void main() {
    vec3 dir = view_dir();
    vec3 d = dir * u_axes;
    float qa = dot(d, d);
    float qb = dot(u_eye, d);
    float disc = qb * qb - qa * u_qc;
    float t_end = 1.0e30;
    if (disc > 0.0 && qb < 0.0) {
        t_end = (-qb - sqrt(disc)) / qa;
    }
    vec3 pass;
    // Мягкое насыщение вместо обрезки: при обрезке зелёный упирался
    // в 1 раньше синего, и в середине неба шла бирюзовая полоса.
    vec3 light = air(dir, t_end, pass);
    frag_color = vec4(1.0 - exp(-SKY_EXPOSURE * light), 1.0);
}
"""

HOLE_VERTEX = """#version 330 core
// Полноэкранный треугольник на глубине 1.0 без буфера вершин.
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 1.0, 1.0);
}
"""

HOLE_FRAGMENT = """#version 330 core
// Пиксель, где не нарисован ни один тайл, а луч попадает в эллипсоид.
// Эллипсоид сжат на u_margin, это отрезает полосу у края диска, где
// хорды тайлов законно лежат внутри эллипсоида. Координаты - в долях
// полуосей сжатого эллипсоида, начало луча - глаз.
uniform mat3 u_rotation;   // оси камеры в ECEF, по столбцам
uniform vec2 u_tan;        // tan(fov/2)·aspect и tan(fov/2)
uniform vec2 u_viewport;   // размер кадра в пикселях
uniform vec3 u_eye;        // глаз в долях полуосей
uniform vec3 u_axes;       // 1 / полуоси
uniform float u_qc;        // |eye|² - 1, посчитано в double
out vec4 frag_color;
void main() {
    vec2 ndc = gl_FragCoord.xy / u_viewport * 2.0 - 1.0;
    vec3 dir = u_rotation * vec3(ndc.x * u_tan.x, ndc.y * u_tan.y, -1.0);
    vec3 d = dir * u_axes;
    float qa = dot(d, d);
    float qb = 2.0 * dot(u_eye, d);
    float disc = qb * qb - 4.0 * qa * u_qc;
    if (disc < 0.0 || qb >= 0.0) {
        discard;
    }
    frag_color = vec4(1.0, 0.0, 1.0, 1.0);
}
"""

LABEL_VERTEX = """#version 330 core
// Надпись: x, y - вершина в координатах экрана -1..1, их считает
// процессор. Третье число - непрозрачность надписи, она гаснет
// у горизонта.
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_uv;
out vec2 v_uv;
out float v_alpha;
void main() {
    v_uv = a_uv;
    v_alpha = a_position.z;
    gl_Position = vec4(a_position.xy, 0.0, 1.0);
}
"""

LABEL_FRAGMENT = """#version 330 core
// Атлас надписей с премноженной альфой, поэтому множится весь цвет.
in vec2 v_uv;
in float v_alpha;
uniform sampler2D u_atlas;
out vec4 frag_color;
void main() {
    frag_color = texture(u_atlas, v_uv) * v_alpha;
}
"""

POINT_VERTEX = """#version 330 core
// Проверочная точка пункта для запроса видимости, в координатах
// экрана -1..1 с глубиной. Цвет не пишется.
layout(location = 0) in vec3 a_position;
void main() {
    gl_Position = vec4(a_position, 1.0);
}
"""

POINT_FRAGMENT = """#version 330 core
out vec4 frag_color;
void main() {
    frag_color = vec4(1.0);
}
"""

TILE_FRAGMENT = """#version 330 core
in vec2 v_uv;
in float v_shade;
in float v_depth;
uniform sampler2D u_texture;
// Наложение: картинка слоя QGIS с премноженной альфой. Координаты
// в ней - u_overlay_uv.xy + u_overlay_uv.z * v_uv, это часть картинки
// предка, пока своя не готова. Без наложения - прозрачная текстура.
uniform sampler2D u_overlay;
uniform vec4 u_overlay_uv;
out vec4 frag_color;
""" + ATMOSPHERE + """
void main() {
    vec4 over = texture(u_overlay, u_overlay_uv.xy + u_overlay_uv.z * v_uv);
    vec3 base = texture(u_texture, v_uv).rgb * (1.0 - over.a) + over.rgb;
    // Отмывка рельефа: множитель яркости, на равнине 1.
    vec3 ground = clamp(base * v_shade, 0.0, 1.0);
    // Дымка: воздух между глазом и поверхностью.
    vec3 pass;
    // Белая подложка под дымкой остаётся белой: pass + (1 - pass) = 1.
    vec3 light = air(view_dir(), v_depth, pass);
    frag_color = vec4(min(ground * pass + light, vec3(1.0)), 1.0);
}
"""


# Свои объекты: линии и заливка многоугольников. Вершина - смещение
# от центра объекта в float32, u_mv - вид из глаза на центр, сдвиг
# «центр - глаз» в нём посчитан в float64. Точка подтягивается к глазу
# на долю u_pull расстояния. Сетка тайла собрана по высотам в своих
# узлах, объект - по высотам в своих точках. Между узлами рельеф
# тайла бывает выше линии, без подтяжки она тонет в склоне.
FEATURE_VERTEX = """
#version 330 core
layout(location = 0) in vec3 a_position;
uniform mat4 u_mv;
uniform mat4 u_projection;
uniform float u_pull;
void main() {
    vec4 eye = u_mv * vec4(a_position, 1.0);
    eye.xyz *= 1.0 - u_pull;
    gl_Position = u_projection * eye;
}
"""

# Отрезок в полосу толщиной u_width пикселей кадра. OpenGL 3.3 Core
# толстых линий не рисует. Концы продлены на полтолщины, так стыки
# соседних отрезков закрыты. Отрезок за ближней плоскостью пропускается.
FEATURE_LINE_GEOMETRY = """
#version 330 core
layout(lines) in;
layout(triangle_strip, max_vertices = 4) out;
uniform vec2 u_viewport;
uniform float u_width;
void main() {
    vec4 a = gl_in[0].gl_Position;
    vec4 b = gl_in[1].gl_Position;
    if (a.w <= 0.0 || b.w <= 0.0) return;
    vec2 half_size = 0.5 * u_viewport;
    vec2 sa = a.xy / a.w * half_size;
    vec2 sb = b.xy / b.w * half_size;
    vec2 d = sb - sa;
    float len = length(d);
    d = len > 1e-6 ? d / len : vec2(1.0, 0.0);
    vec2 n = vec2(-d.y, d.x) * (0.5 * u_width);
    vec2 e = d * (0.5 * u_width);
    vec2 shift[4] = vec2[4](-e + n, -e - n, e + n, e - n);
    for (int i = 0; i < 4; i++) {
        vec4 p = i < 2 ? a : b;
        gl_Position = vec4(p.xy + shift[i] / half_size * p.w, p.zw);
        EmitVertex();
    }
    EndPrimitive();
}
"""

FEATURE_FRAGMENT = """
#version 330 core
uniform vec4 u_color;
out vec4 frag;
void main() {
    frag = u_color;
}
"""