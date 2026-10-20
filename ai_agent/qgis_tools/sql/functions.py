# The virtual layer hands every QGIS expression function to SQLite: a query may call only those reviewed as pure.

from qgis.core import QgsExpression

PURE_GROUPS = (
    "abs acos asin atan atan2 ceil clamp cos degrees exp floor ln log log10 max min pi radians rand randf round",
    "scale_cubic_bezier scale_exp scale_exponential scale_linear scale_polynomial sin sqrt tan",
    "extract_degrees extract_minutes extract_seconds from_base64 hash md5 sha256 to_base64",
    "to_bool tobool to_date todate to_datetime todatetime to_decimal todecimal to_dm todm to_dms todms",
    "to_int toint to_interval tointerval to_real toreal to_string tostring to_time totime",
    "coalesce if nullif regexp_match collect count sum",
    "age convert_timezone datetime_from_epoch day day_of_week epoch get_timezone hour make_date make_datetime",
    "make_interval make_time minute month now second set_timezone timezone_from_id timezone_id week year",
    "ascii char concat concat_ws format format_date format_number left _left length lower lpad ltrim",
    "regexp_replace regexp_substr repeat replace reverse right _right rpad rtrim strpos substr substr_count",
    "title trim unaccent upper wordwrap hamming_distance levenshtein longest_common_substring soundex",
    "color_cmyk color_cmyka color_cmykf color_grayscale_average color_hsl color_hsla color_hslf color_hsv",
    "color_hsva color_hsvf color_mix color_mix_rgb color_part color_rgb color_rgba color_rgbf darker lighter",
    "set_color_part",
    "array array_all array_append array_cat array_contains array_count array_distinct array_find array_first",
    "array_get array_insert array_intersect array_last array_length array_majority array_max array_mean",
    "array_median array_min array_minority array_prepend array_prioritize array_remove_all array_remove_at",
    "array_replace array_reverse array_slice array_sort array_sum array_to_string generate_series",
    "geometries_to_array regexp_matches string_to_array",
    "from_json json_to_map hstore_to_map map map_akeys map_avals map_concat map_delete map_exist map_get",
    "map_insert map_prefix_keys map_to_hstore map_to_html_dl map_to_html_table map_to_json to_json url_encode",
    "crs_from_text mime_type uuid",
    "affine_transform angle_at_vertex apply_dash_pattern area azimuth bbox bearing boundary bounds",
    "bounds_height bounds_width buffer buffer_by_m centroid close_line closest_point collect_geometries combine",
    "concave_hull contains convex_hull convexhull crosses densify_by_count densify_by_distance difference",
    "disjoint distance distance_to_vertex end_point equals equals_exact equals_fuzzy equals_topological",
    "exterior_ring extend extrude flip_coordinates force_polygon_ccw force_polygon_cw force_rhr geom_from_gml",
    "geomfromgml geom_from_wkb geom_from_wkt geomfromwkt geom_to_wkb geom_to_wkt geomtowkt geometry_n",
    "geometry_type hausdorff_distance inclination interior_ring_n intersection intersects intersects_bbox",
    "is_closed is_empty is_empty_or_null is_multipart is_valid length3d line_interpolate_angle",
    "line_interpolate_point line_interpolate_point_by_m line_locate_m line_locate_point line_merge",
    "line_substring m m_at m_max m_min main_angle make_circle make_ellipse make_line make_point make_point_m",
    "make_polygon make_rectangle_3points make_regular_polygon make_square make_triangle make_valid",
    "minimal_circle nodes_to_points num_geometries num_interior_rings num_points num_rings offset_curve",
    "order_parts oriented_bbox overlaps perimeter point_n point_on_surface pole_of_inaccessibility project",
    "relate rotate roundness scale segments_to_lines shared_paths shortest_line simplify simplify_vw",
    "single_sided_buffer sinuosity smooth square_wave square_wave_randomized start_point straight_distance_2d",
    "sym_difference symdifference tapered_buffer touches transform translate triangular_wave",
    "triangular_wave_randomized union _union wave wave_randomized wedge_buffer within x x_at x_max xmax x_min",
    "xmin y y_at y_max ymax y_min ymin z z_at z_max z_min",
)
PURE_FUNCTIONS = frozenset(name for group in PURE_GROUPS for name in group.split())


def unreviewed_functions(called: list[str]) -> list[str]:
    if not called:
        return []
    registered = _registered_names()
    return [name for name in called if name.lower() in registered and name.lower() not in PURE_FUNCTIONS]


def _registered_names() -> set[str]:
    # Read per query: a plugin may register a Python function at any time.
    names: set[str] = set()
    for function in QgsExpression.Functions():
        for name in (function.name(), *function.aliases()):
            lowered = str(name).lower()
            # QGIS registers names that are SQL keywords (left, right, union) with a leading underscore.
            names.update((lowered, "_" + lowered))
    return names
