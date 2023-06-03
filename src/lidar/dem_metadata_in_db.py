# -*- coding: utf-8 -*-
"""
Created on Wed Nov 10 13:22:27 2021.

@author: pkh35, sli229
"""

import logging
import pathlib
import json
from datetime import datetime
from typing import Tuple, Dict, Any, Union

import geopandas as gpd
import xarray as xr
import rioxarray as rxr
from geoalchemy2 import Geometry
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

from src import config
from src.digitaltwin import setup_environment
import geofabrics.processor

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(levelname)s:%(asctime)s:%(name)s:%(message)s")
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

log.addHandler(stream_handler)

Base = declarative_base()


class HydroDEM(Base):
    """Class used to create 'hydrological_dem' table."""
    __tablename__ = "hydrological_dem"
    unique_id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String)
    file_path = Column(String)
    created_at = Column(DateTime(timezone=True), default=datetime.now(), comment="output created datetime")
    geometry = Column(Geometry("GEOMETRY", srid=2193), comment="catchment area coverage")


def create_hydro_dem_table(engine: Engine) -> None:
    """Create 'hydrological_dem' table in the database if it doesn't exist."""
    HydroDEM.__table__.create(bind=engine, checkfirst=True)


def get_hydro_dem_metadata(
        instructions: Dict[str, Any],
        catchment_boundary: gpd.GeoDataFrame) -> Tuple[str, str, str]:
    """Get the hydrological DEM metadat~a."""
    data_paths: Dict[str, Any] = instructions["instructions"]["data_paths"]
    result_dem_path = pathlib.Path(data_paths["local_cache"]) / data_paths["subfolder"] / data_paths["result_dem"]
    hydro_dem_name = result_dem_path.name
    hydro_dem_path = result_dem_path.as_posix()
    catchment_geom = catchment_boundary["geometry"].to_wkt().iloc[0]
    return hydro_dem_name, hydro_dem_path, catchment_geom


def store_hydro_dem_metadata_to_db(
        engine: Engine,
        instructions: Dict[str, Any],
        catchment_boundary: gpd.GeoDataFrame) -> None:
    """Store metadata of the hydrologically conditioned DEM in the database."""
    create_hydro_dem_table(engine)
    hydro_dem_name, hydro_dem_path, geometry = get_hydro_dem_metadata(instructions, catchment_boundary)
    with Session(engine) as session:
        hydro_dem = HydroDEM(file_name=hydro_dem_name, file_path=hydro_dem_path, geometry=geometry)
        session.add(hydro_dem)
        session.commit()
        log.info("Hydro DEM metadata for the catchment area successfully stored in the database.")


def check_hydro_dem_exist(engine: Engine, catchment_boundary: gpd.GeoDataFrame) -> bool:
    """Check if hydro DEM already exists in the database for the catchment area."""
    create_hydro_dem_table(engine)
    catchment_geom = catchment_boundary["geometry"].iloc[0]
    query = f"""
    SELECT EXISTS (
    SELECT 1
    FROM hydrological_dem
    WHERE ST_Equals(geometry, ST_GeomFromText('{catchment_geom}', 2193))
    );"""
    return engine.execute(query).scalar()


def read_and_fill_instructions(catchment_file_path: pathlib.Path) -> Dict[str, Any]:
    """Reads instruction file and adds keys and uses selected_polygon.geojson as catchment_boundary"""
    linz_api_key = config.get_env_variable("LINZ_API_KEY")
    instruction_file = pathlib.Path("src/flood_model/instructions_geofabrics.json")
    with open(instruction_file, "r") as file_pointer:
        instructions = json.load(file_pointer)
        instructions["instructions"]["apis"]["vector"]["linz"]["key"] = linz_api_key
        instructions["instructions"]["data_paths"]["catchment_boundary"] = catchment_file_path.as_posix()
        instructions["instructions"]["data_paths"]["local_cache"] = instructions["instructions"]["data_paths"][
            "local_cache"].format(data_dir=config.get_env_variable("DATA_DIR"))
    return instructions


def create_temp_catchment_boundary_file(selected_polygon_gdf: gpd.GeoDataFrame) -> pathlib.Path:
    """Temporary catchment file to be ingested by GeoFabrics"""
    temp_dir = pathlib.Path("tmp/geofabrics_polygons")
    # Create temporary storage folder if it does not already exist
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / "selected_polygon.geojson"
    selected_polygon_gdf.to_file(temp_file_path.as_posix(), driver='GeoJSON')
    return pathlib.Path.cwd() / temp_file_path


def remove_temp_catchment_boundary_file(file_path: pathlib.Path) -> None:
    """Removes the temporary file from the file system once it is used"""
    file_path.unlink()


def run_geofabrics_hydro_dem(instructions: Dict[str, Any]) -> None:
    """Use geofabrics to generate the hydrologically conditioned DEM."""
    runner = geofabrics.processor.RawLidarDemGenerator(instructions["instructions"])
    runner.run()
    runner = geofabrics.processor.HydrologicDemGenerator(instructions["instructions"])
    runner.run()
    log.info("Hydro DEM for the catchment area successfully generated.")


def generate_hydro_dem(
        engine: Engine,
        instructions: Dict[str, Any],
        catchment_boundary: gpd.GeoDataFrame) -> None:
    """Generate the hydrologically conditioned DEM for the catchment area."""
    if not check_hydro_dem_exist(engine, catchment_boundary):
        run_geofabrics_hydro_dem(instructions)
        store_hydro_dem_metadata_to_db(engine, instructions, catchment_boundary)
    else:
        log.info("Hydro DEM for the catchment area already exists in the database.")


def get_catchment_hydro_dem_filepath(
        engine: Engine,
        catchment_boundary: gpd.GeoDataFrame) -> pathlib.Path:
    """Get the hydro DEM file path for the catchment area."""
    catchment_geom = catchment_boundary["geometry"].iloc[0]
    query = f"""
    SELECT file_path
    FROM hydrological_dem
    WHERE ST_Equals(geometry, ST_GeomFromText('{catchment_geom}', 2193));"""
    hydro_dem_filepath = engine.execute(query).scalar()
    return pathlib.Path(hydro_dem_filepath)


def get_hydro_dem_resolution_from_instruction_file() -> int:
    # Get resolution used for hydro DEM from instructions file
    instruction_file_path = pathlib.Path("src/flood_model/instructions_geofabrics.json")
    with open(instruction_file_path, "r") as instruction_file:
        instructions = json.load(instruction_file)
        resolution = instructions["instructions"]["output"]["grid_params"]["resolution"]
    return resolution


def get_hydro_dem_data(engine: Engine, catchment_boundary: gpd.GeoDataFrame) -> xr.Dataset:
    hydro_dem_filepath = get_catchment_hydro_dem_filepath(engine, catchment_boundary)
    hydro_dem = rxr.open_rasterio(hydro_dem_filepath)
    hydro_dem = hydro_dem.sel(band=1)
    return hydro_dem


def get_hydro_dem_data_and_resolution(
        engine: Engine,
        catchment_boundary: gpd.GeoDataFrame) -> Tuple[xr.Dataset, Union[int, float]]:
    hydro_dem = get_hydro_dem_data(engine, catchment_boundary)
    unique_resolutions = list(set(abs(res) for res in hydro_dem.rio.resolution()))
    res_no = unique_resolutions[0] if len(unique_resolutions) == 1 else None
    res_description = int(hydro_dem.description.split()[-1])
    if res_no != res_description:
        raise ValueError("Inconsistent resolution.")
    else:
        return hydro_dem, res_no


def main(selected_polygon_gdf: gpd.GeoDataFrame) -> None:
    engine = setup_environment.get_database()
    catchment_file_path = create_temp_catchment_boundary_file(selected_polygon_gdf)
    instructions = read_and_fill_instructions(catchment_file_path)
    generate_hydro_dem(engine, instructions, selected_polygon_gdf)
    remove_temp_catchment_boundary_file(catchment_file_path)


if __name__ == "__main__":
    sample_polygon = gpd.GeoDataFrame.from_file("selected_polygon.geojson")
    main(sample_polygon)
