import folium
import geopandas as gpd

shapefile_path = './shapefile/edmonton.shp'
gdf = gpd.read_file(shapefile_path)
gdf = gdf.set_crs('EPSG:4326', allow_override=True).to_crs('EPSG:4326')

# Convert the GeoDataFrame to GeoJSON
geojson_data = gdf.to_json()

# Combine all shapes into a single geometry and calculate the centroid
combined_shape = gdf.union_all()
combined_centroid = combined_shape.centroid

# Note the coordinates have to be reversed
m = folium.Map(location=[combined_centroid.y, combined_centroid.x], zoom_start=11)

folium.GeoJson(
    geojson_data,
    name='geojson'
).add_to(m)

tooltip = folium.GeoJsonTooltip(
    fields=['descriptiv'],
    aliases=[''],
    sticky=False,
    style=(
        "background-color: white; color: black; font-family: arial; font-size: 16px; padding: -2px;"
    ),
)

folium.GeoJson(
    geojson_data,
    name='geojson',
    tooltip=tooltip
).add_to(m)

folium.LayerControl().add_to(m)

map_file = "map.html"
m.save(map_file)