import pytest
from shapely.geometry import Point
from kerala_land_lab.data import coordinates, parse_kml


def test_polygon_hole_is_not_classified_as_hazard():
    xml = b'''<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>High Hazard Zone</name><Polygon>
    <outerBoundaryIs><LinearRing><coordinates>75,10 76,10 76,11 75,11 75,10</coordinates></LinearRing></outerBoundaryIs>
    <innerBoundaryIs><LinearRing><coordinates>75.2,10.2 75.8,10.2 75.8,10.8 75.2,10.8 75.2,10.2</coordinates></LinearRing></innerBoundaryIs>
    </Polygon></Placemark></kml>'''
    rows = parse_kml(xml, "test", None)
    assert rows[0]["source_label"] == "High Hazard Zone"
    assert not rows[0]["geometry"].intersects(Point(75.5, 10.5))
    assert rows[0]["geometry"].intersects(Point(75.1, 10.1))


def test_missing_polygon_fails_instead_of_silent_data_loss():
    with pytest.raises(ValueError, match="without polygon"):
        parse_kml(b'<kml><Placemark><name>hazard</name></Placemark></kml>', "test", None)


def test_invalid_coordinates_rejected():
    with pytest.raises(ValueError):
        coordinates("181,10,0")
