# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тексты шейдеров GLSL 330.

Вершина тайла приходит смещением от центра тайла в float32. Матрица
u_mvp уже включает сдвиг «центр тайла - глаз», посчитанный в float64.
"""

TILE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec2 a_uv;
uniform mat4 u_mvp;
out vec2 v_uv;
void main() {
    v_uv = a_uv;
    gl_Position = u_mvp * vec4(a_position, 1.0);
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

TILE_FRAGMENT = """#version 330 core
in vec2 v_uv;
uniform sampler2D u_texture;
out vec4 frag_color;
void main() {
    frag_color = vec4(texture(u_texture, v_uv).rgb, 1.0);
}
"""
