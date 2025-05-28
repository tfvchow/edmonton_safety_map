from flask import Flask, render_template, request
import csv
import math
import shapefile


def mercator_to_latlon(x, y):
    """Convert Web Mercator (EPSG:3857) to latitude and longitude."""
    r = 6378137
    lon = (x / r) * 180 / math.pi
    lat = (2 * math.atan(math.exp(y / r)) - math.pi / 2) * 180 / math.pi
    return lat, lon


# Load shapefile polygons
shapefile_path = './shapefile/edmonton.shp'
try:
    reader = shapefile.Reader(shapefile_path)
except AttributeError as e:
    raise ImportError(
        "pyshp is required to read shapefiles. Install it using 'pip install pyshp'."
    ) from e

fields = [f[0] for f in reader.fields[1:]]
shapes = []
all_points = []

def polygons_from_geom(geom):
    if geom['type'] == 'Polygon':
        return [geom['coordinates'][0]]
    if geom['type'] == 'MultiPolygon':
        return [p[0] for p in geom['coordinates']]
    return []

for sr in reader.shapeRecords():
    properties = dict(zip(fields, sr.record))
    geometry = sr.shape.__geo_interface__
    polygons = polygons_from_geom(geometry)
    shapes.append((int(properties['neighbourh']), geometry, polygons, properties))
    for poly in polygons:
        all_points.extend(poly)

# Convert shapes to GeoJSON and compute combined centroid
geojson_data = {
    'type': 'FeatureCollection',
    'features': []
}
for idx, geom, _, props in shapes:
    feature = {
        'type': 'Feature',
        'id': idx,
        'properties': props,
        'geometry': geom,
    }
    geojson_data['features'].append(feature)

min_x = min(p[0] for p in all_points)
min_y = min(p[1] for p in all_points)
max_x = max(p[0] for p in all_points)
max_y = max(p[1] for p in all_points)
center_lat = (min_y + max_y) / 2
center_lon = (min_x + max_x) / 2

# Load CSV data
data_path = './data/edmonton_safety_data.csv'
records = []
with open(data_path, newline='', encoding='utf-8') as f:
    reader_csv = csv.DictReader(f)
    for row in reader_csv:
        lat, lon = mercator_to_latlon(float(row['x']), float(row['y']))
        row['point'] = (lon, lat)
        records.append(row)

# Spatial join: assign neighbourhood to each record
def point_in_polygon(point, polygon):
    x, y = point
    inside = False
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        if (y1 > y) != (y2 > y):
            xinters = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xinters:
                inside = not inside
    return inside

for row in records:
    for neigh_id, _, polygons, _ in shapes:
        for poly in polygons:
            if point_in_polygon(row['point'], poly):
                row['neighbourh'] = neigh_id
                break
        if 'neighbourh' in row:
            break

app = Flask(__name__)


def unique_values(records, key):
    return sorted({r[key] for r in records})


@app.route('/', methods=['GET', 'POST'])
def iframe():
    categories = unique_values(records, 'Occurrence_Category')
    groups = unique_values(records, 'Occurrence_Group')
    type_groups = unique_values(records, 'Occurrence_Type_Group')

    selected_categories = request.form.getlist('categories')
    selected_groups = request.form.getlist('groups')
    selected_type_groups = request.form.getlist('type_groups')

    filtered = []
    for row in records:
        if selected_categories and row['Occurrence_Category'] not in selected_categories:
            continue
        if selected_groups and row['Occurrence_Group'] not in selected_groups:
            continue
        if selected_type_groups and row['Occurrence_Type_Group'] not in selected_type_groups:
            continue
        filtered.append(row)

    counts = {}
    for row in filtered:
        n = row.get('neighbourh')
        if n is not None:
            counts[n] = counts.get(n, 0) + 1

    min_val = min(counts.values()) if counts else 0
    max_val = max(counts.values()) if counts else 1

    def style_function(feature):
        n = feature['id']
        val = counts.get(n, 0)
        # Simple linear scale from green (low) to red (high)
        ratio = 0 if max_val == min_val else (val - min_val) / (max_val - min_val)
        red = int(255 * ratio)
        green = int(255 * (1 - ratio))
        color = f'#{red:02x}{green:02x}00'
        return {
            'fillColor': color,
            'color': 'black',
            'weight': 1,
            'fillOpacity': 0.7,
        }

    tooltip = folium.GeoJsonTooltip(
        fields=['descriptiv'],
        aliases=[''],
        sticky=False,
        style="background-color: white; color: black; font-family: arial; font-size: 16px; padding: -2px;",
    )

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    folium.GeoJson(
        geojson_data,
        tooltip=tooltip,
        style_function=style_function,
        name='neighbourhoods',
    ).add_to(m)

    folium.LayerControl().add_to(m)

    m.get_root().width = '1100px'
    m.get_root().height = '1000px'
    iframe = m.get_root()._repr_html_()

    return render_template(
        'index.html',
        categories=categories,
        groups=groups,
        type_groups=type_groups,
        selected_categories=selected_categories,
        selected_groups=selected_groups,
        selected_type_groups=selected_type_groups,
        iframe=iframe,
    )


if __name__ == '__main__':
    app.run(debug=True)
