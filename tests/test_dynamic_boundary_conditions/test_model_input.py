import unittest
import pathlib
from shapely.geometry import Polygon
import geopandas as gpd
import pandas as pd
import numpy as np
from unittest.mock import patch
from src.dynamic_boundary_conditions import model_input


class ModelInputTest(unittest.TestCase):
    """Tests for model_input.py."""

    @staticmethod
    def get_catchment_polygon(filepath: str) -> Polygon:
        """
        Get the catchment boundary geometry (polygon).

        Parameters
        ----------
        filepath
            The file path of the catchment polygon GeoJSON data file.
        """
        catchment_file = pathlib.Path(filepath)
        catchment = gpd.read_file(catchment_file)
        catchment = catchment.to_crs(4326)
        catchment_polygon = catchment["geometry"][0]
        return catchment_polygon

    @classmethod
    def setUpClass(cls):
        """Get all relevant data used for testing."""
        cls.selected_polygon = cls.get_catchment_polygon(
            r"tests/test_dynamic_boundary_conditions/data/selected_polygon.geojson")
        cls.sites_in_catchment = gpd.read_file(
            r"tests/test_dynamic_boundary_conditions/data/sites_in_catchment.geojson")
        cls.intersections = gpd.read_file(
            r"tests/test_dynamic_boundary_conditions/data/intersections.geojson")
        cls.sites_coverage = gpd.read_file(
            r"tests/test_dynamic_boundary_conditions/data/sites_coverage.geojson")
        cls.hyetograph_data_alt_block = pd.read_csv(
            r"tests/test_dynamic_boundary_conditions/data/hyetograph_data_alt_block.txt")
        cls.hyetograph_data_chicago = pd.read_csv(
            r"tests/test_dynamic_boundary_conditions/data/hyetograph_data_chicago.txt")

    def test_sites_voronoi_intersect_catchment_in_catchment(self):
        intersections = model_input.sites_voronoi_intersect_catchment(self.sites_in_catchment, self.selected_polygon)
        self.assertTrue(intersections.within(self.selected_polygon.buffer(1 / 1e13)).unique())

    @patch("src.dynamic_boundary_conditions.model_input.sites_voronoi_intersect_catchment")
    def test_sites_coverage_in_catchment_correct_area_percent(self, mock_intersections):
        mock_intersections.return_value = self.intersections.copy()
        sites_coverage = model_input.sites_coverage_in_catchment(
            sites_in_catchment=gpd.GeoDataFrame(),
            catchment_polygon=Polygon())

        sites_area = (self.intersections.to_crs(3857).area / 1e6)
        sites_area_percent = sites_area / sites_area.sum()
        pd.testing.assert_series_equal(sites_area_percent, sites_coverage["area_percent"], check_names=False)
        self.assertEqual(1, sites_coverage["area_percent"].sum())

    def test_mean_catchment_rainfall_correct_length_and_calculation(self):
        hyetograph_data_list = [self.hyetograph_data_alt_block, self.hyetograph_data_chicago]

        for hyetograph_data in hyetograph_data_list:
            mean_catchment_rain = model_input.mean_catchment_rainfall(hyetograph_data, self.sites_coverage)
            self.assertEqual(len(hyetograph_data), len(mean_catchment_rain))

            for row_index in [0, -1]:
                hyeto_data = hyetograph_data.iloc[row_index, :-3]
                hyeto_data = hyeto_data.to_frame(name="rain_intensity_mmhr").reset_index(names="site_id")
                site_area_percent = self.sites_coverage[["site_id", "area_percent"]]
                hyeto_data = pd.merge(hyeto_data, site_area_percent, how="left", on="site_id")
                row_mean_catchment_rain = (hyeto_data["rain_intensity_mmhr"] * hyeto_data["area_percent"]).sum()
                self.assertEqual(
                    round(row_mean_catchment_rain, 6),
                    round(mean_catchment_rain["rain_intensity_mmhr"].iloc[row_index], 6))

    def test_create_rain_data_cube_correct_intensity_in_data_cube(self):
        hyetograph_data_list = [self.hyetograph_data_alt_block, self.hyetograph_data_chicago]

        for hyetograph_data in hyetograph_data_list:
            for row_index in [0, -1]:
                row_unique_intensity = np.sort(hyetograph_data.iloc[row_index, :-3].unique()).tolist()
                rain_data_cube = model_input.create_rain_data_cube(hyetograph_data, self.sites_coverage)
                time_slice = rain_data_cube.sel(time=hyetograph_data.iloc[row_index]["seconds"])
                time_slice_intensity = time_slice.data_vars["rain_intensity_mmhr"]
                time_slice_unique_intensity = np.unique(time_slice_intensity)[np.unique(time_slice_intensity) != 0]
                time_slice_unique_intensity = np.sort(time_slice_unique_intensity).tolist()
                self.assertEqual(row_unique_intensity, time_slice_unique_intensity)


if __name__ == "__main__":
    unittest.main()
