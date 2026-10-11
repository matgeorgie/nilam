"""Building-footprint construction backed by GEOS/Shapely topology."""
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.validation import explain_validity
from .schemas import HouseShape, HouseFootprint, SiteConstraints


def footprint_polygon(footprint: HouseFootprint) -> Polygon:
    """Return the canonical polygon, including a true courtyard hole."""
    holes = [footprint.courtyard] if footprint.shape == HouseShape.COURTYARD and footprint.courtyard else None
    return Polygon(footprint.boundary, holes=holes)


def _largest_polygon(geometry) -> Polygon:
    if isinstance(geometry, Polygon):
        return geometry
    if isinstance(geometry, MultiPolygon) and geometry.geoms:
        return max(geometry.geoms, key=lambda item: item.area)
    raise ValueError('The requested footprint does not leave a usable building polygon.')


def generate_footprint(
    shape: HouseShape,
    plot_width: float,
    plot_length: float,
    params: dict,
    constraints: SiteConstraints | None = None,
    plot_polygon: list[tuple[float, float]] | None = None,
) -> HouseFootprint:
    constraints = constraints or SiteConstraints()
    if shape == HouseShape.AUTO:
        raise ValueError('Auto is a candidate-search strategy, not a concrete building footprint.')

    plot = Polygon(plot_polygon) if plot_polygon else box(0, 0, plot_width, plot_length)
    if not plot.is_valid or plot.area <= 0:
        raise ValueError(f'Plot polygon is invalid: {explain_validity(plot)}')

    if plot_polygon:
        clearance=max(constraints.front_setback,constraints.rear_setback,constraints.left_setback,constraints.right_setback)
        buildable=_largest_polygon(plot.buffer(-clearance, join_style='mitre')) if clearance else plot
        bx,by,maxx,maxy=buildable.bounds
    else:
        bx=constraints.left_setback;by=constraints.rear_setback
        maxx=plot_width-constraints.right_setback;maxy=plot_length-constraints.front_setback
        buildable=box(bx,by,maxx,maxy)
    W=maxx-bx;L=maxy-by
    if W < 10 or L < 10:
        raise ValueError('Available building area is too small after setbacks.')

    courtyard = None
    if shape == HouseShape.RECTANGLE:
        local=[(0,0),(W,0),(W,L),(0,L)];metrics={'W':W,'L':L}
    elif shape == HouseShape.L_SHAPE:
        arm_w=max(.25*W,min(.75*W,W*params.get('horizontal_arm_ratio',.5)))
        arm_l=max(.25*L,min(.75*L,L*params.get('vertical_arm_ratio',.5)))
        local=[(0,0),(W,0),(W,arm_l),(arm_w,arm_l),(arm_w,L),(0,L)]
        metrics={'arm_w':arm_w,'arm_l':arm_l,'W':W,'L':L}
    elif shape == HouseShape.T_SHAPE:
        top_l=max(.25*L,min(.75*L,L*params.get('top_depth_ratio',.4)))
        stem_w=max(.5*W,min(.85*W,W*params.get('stem_width_ratio',.8)))
        stem_x=(W-stem_w)/2
        local=[(0,0),(W,0),(W,top_l),(stem_x+stem_w,top_l),(stem_x+stem_w,L),(stem_x,L),(stem_x,top_l),(0,top_l)]
        metrics={'top_l':top_l,'stem_w':stem_w,'stem_x':stem_x,'W':W,'L':L}
    elif shape == HouseShape.U_SHAPE:
        left_w=max(.3*W,min(.45*W,W*params.get('left_wing_ratio',.4)))
        right_w=max(.3*W,min(.45*W,W*params.get('right_wing_ratio',.4)))
        rear_l=max(.25*L,min(.6*L,L*params.get('rear_wing_ratio',.4)))
        local=[(0,0),(W,0),(W,L),(W-right_w,L),(W-right_w,rear_l),(left_w,rear_l),(left_w,L),(0,L)]
        courtyard=[(left_w,rear_l),(W-right_w,rear_l),(W-right_w,L),(left_w,L)]
        metrics={'left_w':left_w,'right_w':right_w,'rear_l':rear_l,'W':W,'L':L}
    elif shape == HouseShape.C_SHAPE:
        side_w=max(.35*W,min(.55*W,W*params.get('side_wing_ratio',.5)))
        top_l=max(.2*L,min(.4*L,L*params.get('top_wing_ratio',.3)))
        bottom_l=max(.2*L,min(.4*L,L*params.get('bottom_wing_ratio',.3)))
        local=[(0,0),(W,0),(W,bottom_l),(side_w,bottom_l),(side_w,L-top_l),(W,L-top_l),(W,L),(0,L)]
        courtyard=[(side_w,bottom_l),(W,bottom_l),(W,L-top_l),(side_w,L-top_l)]
        metrics={'side_w':side_w,'top_l':top_l,'bottom_l':bottom_l,'W':W,'L':L}
    elif shape == HouseShape.STEPPED:
        step1=max(.6*W,min(.9*W,W*params.get('middle_width_ratio',.8)))
        step2=max(.45*W,min(step1-2,W*params.get('upper_width_ratio',.62)))
        d1=L*params.get('lower_depth_ratio',.36);d2=L*params.get('middle_depth_ratio',.7)
        local=[(0,0),(W,0),(W,d1),(step1,d1),(step1,d2),(step2,d2),(step2,L),(0,L)]
        metrics={'step1':step1,'step2':step2,'d1':d1,'d2':d2,'W':W,'L':L}
    elif shape == HouseShape.COURTYARD:
        wing_x=max(13,min(W*.45,W*params.get('side_wing_ratio',.43)))
        wing_y=max(12,min(L*.36,L*params.get('end_wing_ratio',.3)))
        if W-2*wing_x<4 or L-2*wing_y<6:
            raise ValueError('Plot is too small for a usable enclosed courtyard.')
        local=[(0,0),(W,0),(W,L),(0,L)]
        courtyard=[(wing_x,wing_y),(W-wing_x,wing_y),(W-wing_x,L-wing_y),(wing_x,L-wing_y)]
        metrics={'side_w':wing_x,'end_l':wing_y,'W':W,'L':L}
    else:
        raise ValueError(f'Unsupported footprint shape: {shape.value}')

    boundary=[(x+bx,y+by) for x,y in local]
    courtyard=[(x+bx,y+by) for x,y in courtyard] if courtyard else None
    template=Polygon(boundary, holes=[courtyard] if shape==HouseShape.COURTYARD and courtyard else None)
    clipped=_largest_polygon(template.intersection(buildable))
    if clipped.area < template.area*.65:
        raise ValueError('The irregular plot and setbacks clip too much of this footprint template.')
    boundary=list(clipped.exterior.coords)[:-1]
    if shape==HouseShape.COURTYARD and clipped.interiors:
        courtyard=list(clipped.interiors[0].coords)[:-1]
    minx,miny,outx,outy=clipped.bounds
    metrics.update({'footprint_area':clipped.area,'buildable_area':buildable.area})
    return HouseFootprint(shape=shape,plot_width=plot_width,plot_length=plot_length,boundary=boundary,courtyard=courtyard,buildable_boundary=list(buildable.exterior.coords)[:-1],bounding_box=(minx,miny,outx,outy),metrics=metrics)


def validate_footprint(footprint: HouseFootprint, plot_polygon: list[tuple[float,float]] | None = None) -> list[str]:
    errors=[];poly=footprint_polygon(footprint)
    if not poly.is_valid: errors.append(f'Footprint polygon is invalid: {explain_validity(poly)}')
    if poly.area<100: errors.append('Footprint area is too small.')
    plot=Polygon(plot_polygon) if plot_polygon else box(0,0,footprint.plot_width,footprint.plot_length)
    if not plot.buffer(1e-5).covers(poly): errors.append('Footprint exceeds plot boundaries.')
    return errors
