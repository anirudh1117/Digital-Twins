# -*- coding: utf-8 -*-
"""
@Script name: hyetograph.py
@Description:
@Author: pkh35
@Date: 17/01/2022
@Last modified by: sli229
@Last modified date: 28/09/2022
"""

import geopandas as gpd
import pathlib
from shapely.geometry import Polygon
from src.digitaltwin import setup_environment
from src.dynamic_boundary_conditions import rainfall_sites
from src.dynamic_boundary_conditions import thiessen_polygon_calculator
from src.dynamic_boundary_conditions import hirds_rainfall_data_to_db
from src.dynamic_boundary_conditions import hirds_rainfall_data_from_db


def catchment_area_geometry_info(catchment_file_path) -> Polygon:
    """
    Extract shapely polygon geometry from the catchment file.

    Parameters
    ----------
    catchment_file_path
        The file path of the catchment polygon shapefile.
    """
    catchment = gpd.read_file(catchment_file_path)
    catchment = catchment.to_crs(4326)
    catchment_polygon = catchment["geometry"][0]
    return catchment_polygon


def main():
    catchment_file = pathlib.Path(r"src\dynamic_boundary_conditions\catchment_polygon.shp")
    file_path_to_store = pathlib.Path(r"U:\Research\FloodRiskResearch\DigitalTwin\hirds_rainfall_data")
    rcp = 2.6
    time_period = "2031-2050"
    ari = 100
    # To get rainfall data for all durations set duration to "all"
    duration = "all"

    engine = setup_environment.get_database()
    sites = rainfall_sites.get_rainfall_sites_data()
    rainfall_sites.rainfall_sites_to_db(engine, sites)
    nz_boundary_polygon = rainfall_sites.get_new_zealand_boundary(engine)
    sites_in_catchment = rainfall_sites.get_sites_locations(engine, nz_boundary_polygon)
    thiessen_polygon_calculator.thiessen_polygons(engine, nz_boundary_polygon, sites_in_catchment)
    catchment_polygon = catchment_area_geometry_info(catchment_file)

    # Set idf to False for rain depth data and to True for rain intensity data
    hirds_rainfall_data_to_db.rainfall_data_to_db(engine, catchment_polygon, file_path_to_store, idf=False)
    hirds_rainfall_data_to_db.rainfall_data_to_db(engine, catchment_polygon, file_path_to_store, idf=True)
    rain_depth_in_catchment = hirds_rainfall_data_from_db.rainfall_data_from_db(
        engine, catchment_polygon, rcp, time_period, ari, duration, idf=False)
    print(rain_depth_in_catchment)
    rain_intensity_in_catchment = hirds_rainfall_data_from_db.rainfall_data_from_db(
        engine, catchment_polygon, rcp, time_period, ari, duration, idf=True)
    print(rain_intensity_in_catchment)


if __name__ == "__main__":
    main()
