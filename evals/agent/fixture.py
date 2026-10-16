"""The agent bench's project: the same small city the skill bench describes, as real layers in QGIS.

Districts, roads, schools and stations in GeoPackages, a DEM in a GeoTIFF and
two CSV files beside them. Every value is fixed, so a task can name the exact
outcome: 3 schools hold fewer than 100 pupils, 5 more than 1000, 8 are lyceums.
The project is in Web Mercator, as one that began on a basemap is. Each
district is 0.08° × 0.05°, about 2798 ha on the ellipsoid.
The schools spread unevenly, 0 to 4 per district, as real ones do: an even 2
everywhere once made the model doubt its own count. The task cases in tasks.yaml
rely on these numbers.
"""

import csv
import os
import struct
from typing import Any

from osgeo import gdal, osr
from qgis.core import (
    QgsCoordinateTransformContext,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
)

DISTRICT_NAMES = [
    "Arbat", "Basmanny", "Khamovniki", "Meshchansky", "Presnensky", "Tagansky",
    "Tverskoy", "Yakimanka", "Zamoskvorechye", "Krasnoselsky", "Ostankinsky", "Sokolniki",
]  # fmt: skip
POPULATIONS = [36257, 112512, 110660, 59750, 128510, 122830, 97340, 46210, 103420, 51870, 64930, 58920]
OKRUGS = ["Central", "North", "South"]
COLUMNS = 4
ORIGIN = (37.45, 55.65)
CELL = (0.08, 0.05)
AREA_KM2 = 27.9
HIGHWAYS = ["primary", "secondary", "residential", "footway", "service", "tertiary"]
ROAD_COUNT = 30
SCHOOL_KINDS = ["school", "lyceum", "gymnasium"]
CAPACITIES = [1200, 85, 640, 720, 1100, 450, 95, 880, 530, 1350, 600, 60, 410, 760, 1050, 390, 820, 470, 1500, 680,
              350, 910, 560, 300]  # fmt: skip
# Schools per district, in district order: 24 in all, one district without any.
SCHOOLS_PER_DISTRICT = [4, 1, 3, 2, 0, 2, 3, 1, 2, 4, 1, 1]
STATION_LINES = ["Red", "Green", "Blue"]
STATION_COUNT = 9
UTM_37N = "EPSG:32637"
# What QGIS gives every new project: $area and $length measure on it, in metres, whatever a layer's CRS.
ELLIPSOID = "EPSG:7030"
DEM_SIZE = (80, 60)
DEM_CELL = 250.0
DEM_ORIGIN = (400000.0, 6190000.0)
LAYER_NAMES = ("districts", "roads", "schools", "stations", "dem")
FILES = ("population.csv", "stops.csv")
STOPS = [("1", "Tverskaya", 37.6056, 55.7647), ("2", "Pushkinskaya", 37.6043, 55.7656),
         ("3", "Okhotny Ryad", 37.6153, 55.7576), ("4", "Teatralnaya", 37.6186, 55.7579),
         ("5", "Lubyanka", 37.6268, 55.7597)]  # fmt: skip


def build(folder: str) -> None:
    """Write the layers and files into `folder` and add the layers to the open project."""
    project = QgsProject.instance()
    project.setCrs(project.crs().fromOgcWmsCrs("EPSG:3857"))
    project.setEllipsoid(ELLIPSOID)
    for name, layer in (
        ("districts", _districts()),
        ("roads", _roads()),
        ("schools", _schools()),
        ("stations", _stations()),
    ):
        project.addMapLayer(QgsVectorLayer(_write(layer, folder, name), name, "ogr"))
    project.addMapLayer(QgsRasterLayer(_dem(folder), "dem", "gdal"))
    _csv(folder)
    project.write(os.path.join(folder, "evals.qgz"))


def _cell(index: int) -> tuple[float, float]:
    column, row = index % COLUMNS, index // COLUMNS
    return ORIGIN[0] + CELL[0] * column, ORIGIN[1] + CELL[1] * row


def _districts() -> QgsVectorLayer:
    layer = QgsVectorLayer(
        "Polygon?crs=EPSG:4326&field=name:string&field=okrug:string&field=pop2020:integer&field=area_km2:double",
        "districts",
        "memory",
    )
    features = []
    for index, (name, population) in enumerate(zip(DISTRICT_NAMES, POPULATIONS, strict=True)):
        x, y = _cell(index)
        ring = [
            QgsPointXY(x, y),
            QgsPointXY(x + CELL[0], y),
            QgsPointXY(x + CELL[0], y + CELL[1]),
            QgsPointXY(x, y + CELL[1]),
        ]
        features.append(
            _feature(layer, [name, OKRUGS[index // COLUMNS], population, AREA_KM2], QgsGeometry.fromPolygonXY([ring]))
        )
    layer.dataProvider().addFeatures(features)
    return layer


def _roads() -> QgsVectorLayer:
    layer = QgsVectorLayer(
        "LineString?crs=EPSG:4326&field=name:string&field=highway:string&field=lanes:integer&field=maxspeed:integer",
        "roads",
        "memory",
    )
    features = []
    for index in range(ROAD_COUNT):
        x, y = ORIGIN[0] + 0.01 * index, ORIGIN[1] + 0.005 * (index % 7)
        line = QgsGeometry.fromPolylineXY([QgsPointXY(x, y), QgsPointXY(x + 0.03, y + 0.02)])
        name = "Tverskaya" if index == 0 else f"Street {index + 1}"
        highway = HIGHWAYS[index % len(HIGHWAYS)]
        features.append(_feature(layer, [name, highway, 1 + index % 4, 20 + 10 * (index % 5)], line))
    layer.dataProvider().addFeatures(features)
    return layer


def _schools() -> QgsVectorLayer:
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=name:string&field=kind:string&field=capacity:integer", "schools", "memory"
    )
    # Each school inside its district's cell, spread along the diagonal and away from the edges.
    places = [(district, slot, count) for district, count in enumerate(SCHOOLS_PER_DISTRICT) for slot in range(count)]
    features = []
    for index, (capacity, (district, slot, count)) in enumerate(zip(CAPACITIES, places, strict=True)):
        x, y = _cell(district)
        offset = (slot + 1) / (count + 1)
        point = QgsGeometry.fromPointXY(QgsPointXY(x + CELL[0] * offset, y + CELL[1] * offset))
        kind = SCHOOL_KINDS[index % len(SCHOOL_KINDS)]
        features.append(_feature(layer, [f"{kind.title()} {index + 1}", kind, capacity], point))
    layer.dataProvider().addFeatures(features)
    return layer


def _stations() -> QgsVectorLayer:
    layer = QgsVectorLayer(
        f"Point?crs={UTM_37N}&field=name:string&field=line:string&field=passengers:integer", "stations", "memory"
    )
    features = []
    for index in range(STATION_COUNT):
        point = QgsGeometry.fromPointXY(QgsPointXY(410000 + 1500 * index, 6175000 + 1500 * (index % 3)))
        features.append(
            _feature(layer, [f"Station {index + 1}", STATION_LINES[index % 3], 20000 + 3000 * index], point)
        )
    layer.dataProvider().addFeatures(features)
    return layer


def _feature(layer: QgsVectorLayer, attributes: list[Any], geometry: QgsGeometry) -> QgsFeature:
    feature = QgsFeature(layer.fields())
    feature.setAttributes(attributes)
    feature.setGeometry(geometry)
    return feature


def _write(layer: QgsVectorLayer, folder: str, name: str) -> str:
    path = os.path.join(folder, f"{name}.gpkg")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    QgsVectorFileWriter.writeAsVectorFormatV3(layer, path, QgsCoordinateTransformContext(), options)
    return path


def _dem(folder: str) -> str:
    """A gentle slope in metres, 250 m cells in UTM 37N: enough for a hillshade or a 3D view."""
    path = os.path.join(folder, "dem.tif")
    width, height = DEM_SIZE
    dataset = gdal.GetDriverByName("GTiff").Create(path, width, height, 1, gdal.GDT_Float32)
    dataset.SetGeoTransform([DEM_ORIGIN[0], DEM_CELL, 0, DEM_ORIGIN[1], 0, -DEM_CELL])
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(int(UTM_37N.split(":")[1]))
    dataset.SetProjection(reference.ExportToWkt())
    values = [120.0 + column * 1.0 + row * 0.5 for row in range(height) for column in range(width)]
    band = dataset.GetRasterBand(1)
    band.WriteRaster(0, 0, width, height, struct.pack(f"{len(values)}f", *values))
    band.SetNoDataValue(-9999.0)
    dataset.FlushCache()
    dataset = None
    return path


def _csv(folder: str) -> None:
    with open(os.path.join(folder, "population.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["district", "population_2024"])
        for name, population in zip(DISTRICT_NAMES, POPULATIONS, strict=True):
            writer.writerow([name, round(population * 1.03)])
    with open(os.path.join(folder, "stops.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["stop_id", "name", "lon", "lat"])
        writer.writerows(STOPS)
