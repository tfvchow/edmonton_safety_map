from flask import Flask, render_template, request


import folium
import geopandas as gpd
import pandas as pd

shapefile_path = './shapefile/edmonton.shp'
gdf = gpd.read_file(shapefile_path)
gdf = gdf.set_crs('EPSG:4326', allow_override=True).to_crs('EPSG:4326')
gdf["neighbourh"] = gdf["neighbourh"].astype(int)
gdf.set_index("neighbourh", inplace=True)

YEARS = ["2022", "2023", "2024", "2025"]

# Data files from different years use different coordinate reference systems (CRS).
# Older files (2022–2024) use a local projected CRS while the most recent file
# (2025) is in Web Mercator.  All geometries must end up in WGS84 (EPSG:4326).
YEAR_CRS = {
    # Older CSV files from 2022–2024 use the same projected CRS. Based on the
    # coordinates provided by the City of Edmonton, that CRS is "NAD83 / Alberta
    # 3TM ref merid 114 W" (EPSG:3776).
    "2022": 3776,
    "2023": 3776,
    "2024": 3776,
    # Newer files (2025 and beyond) are published in Web Mercator.
    "2025": 3857,
}

def load_data(year: str) -> gpd.GeoDataFrame:
    """Load the CSV data for the provided year and spatially join it."""
    data_path = f"./data/edmonton_safety_data_{year}.csv"
    data = pd.read_csv(data_path)

    # Determine the CRS to use for this year's data and convert to WGS84.
    crs_from = YEAR_CRS.get(year, 4326)
    points = gpd.GeoDataFrame(
        data,
        geometry=gpd.points_from_xy(data["x"], data["y"]),
        crs=f"EPSG:{crs_from}",
    ).to_crs("EPSG:4326")

    joined = gpd.sjoin(points, gdf, how="inner", predicate="within")
    return joined


# Combine all shapes into a single geometry and calculate the centroid
combined_shape = gdf.union_all()
combined_centroid = combined_shape.centroid

app = Flask(__name__)

@app.route("/", methods=['GET', 'POST'])
def iframe():
    selected_year = request.form.get("year", YEARS[-1])
    filter_by = request.form.get("filter_by", "categories")
    joined = load_data(selected_year)

    # Note the coordinates have to be reversed
    m = folium.Map(location=[combined_centroid.y, combined_centroid.x], zoom_start=11)

    data = joined.drop(columns="geometry")
    categories = sorted(data["Occurrence_Category"].unique())
    type_groups = sorted(data["Occurrence_Type_Group"].unique())

    selected_categories = request.form.getlist("categories") if filter_by == "categories" else []
    selected_type_groups = request.form.getlist("type_groups") if filter_by == "type_groups" else []

    filtered_events = joined

    # Apply exactly one filter based on the active radio selection.
    if selected_categories:
        filtered_events = filtered_events[filtered_events["Occurrence_Category"].isin(selected_categories)]
    elif selected_type_groups:
        filtered_events = filtered_events[filtered_events["Occurrence_Type_Group"].isin(selected_type_groups)]
    counts_by_neighbour = filtered_events.groupby("neighbourh")["Occurrence_Type_Group"].count()

    top_types_df = (
        filtered_events.groupby(["neighbourh", "Occurrence_Type_Group"])\
        .size()\
        .reset_index(name="count")
    )
    # Build HTML tables showing the top 5 incident types per neighbourhood.
    sorted_types = top_types_df.sort_values(["neighbourh", "count"], ascending=[True, False])
    top_types_mapping = {}
    for neigh, df_n in sorted_types.groupby("neighbourh"):
        total = counts_by_neighbour.get(neigh, 0)
        header = "<table style='border-collapse:collapse'>"
        header += "<tr><th>Type</th><th>Count</th><th>%</th></tr>"
        rows = []
        for _, row in df_n.head(5).iterrows():
            pct = (row["count"] / total * 100) if total else 0
            rows.append(
                f"<tr><td>{row['Occurrence_Type_Group']}</td><td>{row['count']}</td><td>{pct:.1f}%</td></tr>"
            )
        table = header + "".join(rows) + "</table>"
        top_types_mapping[neigh] = table

    gdf_counts = gdf.copy()
    gdf_counts["count"] = counts_by_neighbour
    gdf_counts["count"] = gdf_counts["count"].fillna(0).astype(int)
    gdf_counts["top_types"] = gdf_counts.index.map(top_types_mapping).fillna("")
    geojson_data = gdf_counts.to_json()

    tooltip = folium.GeoJsonTooltip(
        fields=["descriptiv", "count", "top_types"],
        aliases=["Community", "Incidents", "Top Types"],
        sticky=False,
        style=(
            "background-color: white; color: black; font-family: arial; font-size: 16px; padding: -2px;"
        ),
    )

    try:
        choropleth = folium.Choropleth(
            geo_data=geojson_data,
            data=counts_by_neighbour,
            key_on='id',
            fill_color='RdYlGn_r',
            use_jenks=True,
        )
    except ValueError:
        choropleth = folium.Choropleth(
            geo_data=geojson_data,
            data=counts_by_neighbour,
            key_on='id',
            fill_color='RdYlGn_r',
        )
        
    choropleth.add_to(m)
    choropleth.geojson.add_child(tooltip)
    choropleth.color_scale.caption = "Incident Count"
    legend_html = choropleth.color_scale._repr_html_()


    folium.LayerControl().add_to(m)

    # set the iframe width and height to fill its container
    m.get_root().width = "100%"
    m.get_root().height = "100%"
    iframe = m.get_root()._repr_html_()

    return render_template(
        'index.html',
        years=YEARS,
        selected_year=selected_year,
        categories=categories,
        type_groups=type_groups,
        filter_by=filter_by,
        selected_categories=selected_categories,
        selected_type_groups=selected_type_groups,
        iframe=iframe,
        legend=legend_html,
    )

if __name__ == "__main__":
    app.run(debug=True)
