from pyproj import Transformer

import folium
import geopandas as gpd
import pandas as pd

shapefile_path = './shapefile/edmonton.shp'
gdf = gpd.read_file(shapefile_path)
gdf = gdf.set_crs('EPSG:4326', allow_override=True).to_crs('EPSG:4326')
gdf["neighbourh"] = gdf["neighbourh"].astype(int)
gdf.set_index("neighbourh", inplace=True)

# Load CSV data
data_path = "./data/edmonton_safety_data.csv"
data = pd.read_csv(data_path)

transformer = Transformer.from_crs(3857, 4326)
data['coordinates'] = data.apply(lambda x: transformer.transform(x['x'], x['y']), axis=1)
points = gpd.GeoDataFrame(data, geometry=gpd.points_from_xy(data.coordinates.str[1], data.coordinates.str[0]))

# Spatial join - points to shapes
joined = gpd.sjoin(points, gdf, how="inner", predicate="within")
joined = joined.groupby('neighbourh')["Occurrence_Type_Group"].count()

# Convert the GeoDataFrame to GeoJSON
geojson_data = gdf.to_json()

# Combine all shapes into a single geometry and calculate the centroid
combined_shape = gdf.union_all()
combined_centroid = combined_shape.centroid

# Note the coordinates have to be reversed
m = folium.Map(location=[combined_centroid.y, combined_centroid.x], zoom_start=11)

tooltip = folium.GeoJsonTooltip(
    fields=['descriptiv'],
    aliases=[''],
    sticky=False,
    style=(
        "background-color: white; color: black; font-family: arial; font-size: 16px; padding: -2px;"
    ),
)

choropleth = folium.Choropleth(
    geo_data=geojson_data,
    data=joined,
    key_on='id',
    fill_color='RdYlGn_r',
    use_jenks=True,
)
choropleth.add_to(m)
choropleth.color_scale.width = 1200

folium.GeoJson(
    geojson_data,
    name='geojson',
    tooltip=tooltip,
    style_function=lambda feature: {
        'fillOpacity': 0.0,
        'opacity': 0.0
    }
).add_to(m)

folium.LayerControl().add_to(m)

map_file = "map.html"
m.save(map_file)