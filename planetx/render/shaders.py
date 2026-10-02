# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тексты шейдеров GLSL 330.

Вершина тайла приходит смещением от центра тайла в float32. Матрица
u_mvp уже включает сдвиг «центр тайла - глаз», посчитанный в float64.
"""

try:  # внутри плагина QGIS
    from ..core import sun as _sun
except ImportError:  # проверки без пакета
    import sun as _sun

SHELL_KM = 300.0  # толщина оболочки атмосферы


def shell(a):
    """Оболочка воздуха в долях полуосей тела с большой полуосью a, м."""
    return 1.0 + SHELL_KM * 1000.0 / a

# Воздух на луче из глаза. Плотность падает с высотой по экспоненте,
# рассеяние по каналам как у рэлеевского на уровне моря. Свет
# рассеивается одинаково во все стороны. При включённом солнце
# воздух над ночной стороной гаснет до AIR_NIGHT. Луч идёт в координатах
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
uniform vec3 u_sun;        // направление на солнце в ECEF
uniform float u_sun_on;    // 1 - свет солнца, 0 - отмывка без солнца
uniform float u_radius_km; // большая полуось тела в километрах
uniform vec3 u_air_tint;   // рассеяние воздуха тела к земному по R, G, B
// Свет солнца, формула core.sun.brightness.
const float SUN_AMBIENT = %(ambient)r;
const float SUN_NIGHT = %(night)r;
const float SUN_FLAT = %(flat)r;
const float TWILIGHT = %(twilight)r;
const float DAYLIGHT = %(daylight)r;
// Ночью воздух светится на эту долю от дневного.
const float AIR_NIGHT = 0.03;

float sun_brightness(float cos_sun) {
    float day = smoothstep(TWILIGHT, DAYLIGHT, cos_sun);
    float ambient = mix(SUN_NIGHT, SUN_AMBIENT, day);
    return (ambient + (1.0 - SUN_AMBIENT) * max(cos_sun, 0.0)) / SUN_FLAT;
}
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
        float h = max(length(p) - 1.0, 0.0) * u_radius_km;
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
    pass = exp(-BETA * u_air_tint * depth);
    vec3 glow = 1.0 - pass;
    if (u_sun_on > 0.5) {
        // Воздух светится, пока над ближней к Земле точкой луча день.
        vec3 up = normalize(u_eye + tc * d);
        glow *= mix(AIR_NIGHT, 1.0,
                    smoothstep(TWILIGHT, DAYLIGHT, dot(up, u_sun)));
    }
    return glow;
}
""" % {"ambient": _sun.AMBIENT, "night": _sun.NIGHT,
       "flat": _sun.FLAT, "twilight": _sun.TWILIGHT,
       "daylight": _sun.DAYLIGHT}

TILE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in float a_shade;
layout(location = 3) in vec3 a_normal;
uniform mat4 u_mvp;
out vec2 v_uv;
out float v_shade;
out vec3 v_normal;
out float v_depth;
void main() {
    v_uv = a_uv;
    v_shade = a_shade;
    v_normal = a_normal;
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
in vec3 v_normal;
in float v_depth;
uniform sampler2D u_texture;
// Наложение: картинка слоя QGIS с премноженной альфой. Координаты
// в ней - u_overlay_uv.xy + u_overlay_uv.z * v_uv, это часть картинки
// предка, пока своя не готова. Без наложения - прозрачная текстура.
uniform sampler2D u_overlay;
uniform vec4 u_overlay_uv;
// Облака поверх подложки и наложения, тоже с премноженной альфой
// и окном в картинке предка, см. render/clouds.py.
uniform sampler2D u_clouds;
uniform vec4 u_clouds_uv;
// Температура моря и суши под наложением, так же, см. render/gibs.py.
uniform sampler2D u_sea;
uniform vec4 u_sea_uv;
uniform sampler2D u_land;
uniform vec4 u_land_uv;
// Уклон или экспозиция по высотам, над температурой, см. core/slope.py.
uniform sampler2D u_slope;
uniform vec4 u_slope_uv;
// Видимость из точки, над уклоном, см. core/viewshed.py.
uniform sampler2D u_viewshed;
uniform vec4 u_viewshed_uv;
// Инсоляция, над видимостью, см. core/insolation.py.
uniform sampler2D u_insolation;
uniform vec4 u_insolation_uv;
out vec4 frag_color;
""" + ATMOSPHERE + """
vec3 lay(vec3 under, sampler2D image, vec4 uv) {
    vec4 top = texture(image, uv.xy + uv.z * v_uv);
    return under * (1.0 - top.a) + top.rgb;
}
void main() {
    vec3 base = texture(u_texture, v_uv).rgb;
    base = lay(base, u_sea, u_sea_uv);
    base = lay(base, u_land, u_land_uv);
    base = lay(base, u_slope, u_slope_uv);
    base = lay(base, u_viewshed, u_viewshed_uv);
    base = lay(base, u_insolation, u_insolation_uv);
    base = lay(base, u_overlay, u_overlay_uv);
    base = lay(base, u_clouds, u_clouds_uv);
    // Отмывка рельефа: множитель яркости, на равнине 1. С солнцем -
    // свет по нормали и направлению на солнце, с ночной стороной.
    float shade = v_shade;
    if (u_sun_on > 0.5) {
        shade = sun_brightness(dot(normalize(v_normal), u_sun));
    }
    vec3 ground = clamp(base * shade, 0.0, 1.0);
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

# 3D-здания, render/buildings.py. Нормаль и цвет - в вершине, нормаль
# в ECEF. Освещение как у отмывки рельефа (core.tiling.shade): свет
# u_light, яркость делится на яркость плоской крыши u_flat, так крыша
# остаётся цвета здания, стены светлее или темнее.
BUILDING_VERTEX = """
#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec4 a_normal;
layout(location = 2) in vec4 a_color;
uniform mat4 u_mvp;
uniform vec3 u_light;
uniform float u_ambient;
uniform float u_flat;
uniform vec2 u_limits;
// С солнцем u_light - направление на солнце, свет по формуле
// core.sun.brightness, ночью дома тёмные.
uniform float u_sun_on;
const float SUN_AMBIENT = %(ambient)r;
const float SUN_NIGHT = %(night)r;
const float SUN_FLAT = %(flat)r;
const float TWILIGHT = %(twilight)r;
const float DAYLIGHT = %(daylight)r;
out vec3 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_position, 1.0);
    vec3 n = a_normal.xyz;
    float len = length(n);
    float shade;
    if (u_sun_on > 0.5) {
        float c = len > 0.0 ? dot(n / len, u_light) : 1.0;
        float day = smoothstep(TWILIGHT, DAYLIGHT, c);
        shade = (mix(SUN_NIGHT, SUN_AMBIENT, day)
                 + (1.0 - SUN_AMBIENT) * max(c, 0.0)) / SUN_FLAT;
    } else {
        float lambert = len > 0.0 ? clamp(dot(n / len, u_light), 0.0, 1.0)
                                  : 1.0;
        shade = clamp((u_ambient + (1.0 - u_ambient) * lambert) / u_flat,
                      u_limits.x, u_limits.y);
    }
    v_color = min(a_color.rgb * shade, vec3(1.0));
}
""" % {"ambient": _sun.AMBIENT, "night": _sun.NIGHT, "flat": _sun.FLAT,
       "twilight": _sun.TWILIGHT, "daylight": _sun.DAYLIGHT}

BUILDING_FRAGMENT = """
#version 330 core
in vec3 v_color;
out vec4 frag;
void main() {
    frag = vec4(v_color, 1.0);
}
"""