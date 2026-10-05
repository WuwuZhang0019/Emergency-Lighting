"""Generate a minimal, synthetic CAD plan. No production parameters or dynamic blocks."""
from pathlib import Path
import json


def build_dxf():
    rows = []
    def tag(code, value):
        rows.extend([str(code), str(value)])
    def line(layer, a, b):
        for code,value in [(0,'LINE'),(100,'AcDbEntity'),(8,layer),(100,'AcDbLine'),(10,a[0]),(20,a[1]),(30,0),
                           (11,b[0]),(21,b[1]),(31,0)]: tag(code,value)
    def polyline(layer, points):
        for code,value in [(0,'LWPOLYLINE'),(100,'AcDbEntity'),(8,layer),
                           (100,'AcDbPolyline'),(90,len(points)),(70,0)]: tag(code,value)
        for x,y in points: tag(10,x); tag(20,y)
    def block(name, corners):
        for code,value in [(0,'BLOCK'),(100,'AcDbEntity'),(8,'0'),(100,'AcDbBlockBegin'),(2,name),(70,0),(10,0),(20,0),(30,0),(3,name),(1,'')]: tag(code,value)
        for a,b in zip(corners,corners[1:]+corners[:1]): line('0',a,b)
        tag(0,'ENDBLK'); tag(100,'AcDbEntity'); tag(8,'0'); tag(100,'AcDbBlockEnd')
    def insert(name, layer, point):
        for code,value in [(0,'INSERT'),(100,'AcDbEntity'),(8,layer),(100,'AcDbBlockReference'),(2,name),(10,point[0]),(20,point[1]),
                           (30,0),(41,1),(42,1),(43,1),(50,0)]: tag(code,value)

    tag(0,'SECTION'); tag(2,'HEADER')
    tag(9,'$ACADVER'); tag(1,'AC1015')
    tag(9,'$INSUNITS'); tag(70,4)
    tag(0,'ENDSEC'); tag(0,'SECTION'); tag(2,'TABLES')
    tag(0,'TABLE'); tag(2,'LAYER'); tag(70,4)
    for name,color in [('0',7),('ELA_PANEL',4),('ELA_WIRE',3),('ELA_DEVICE',2)]:
        for code,value in [(0,'LAYER'),(100,'AcDbSymbolTableRecord'),(100,'AcDbLayerTableRecord'),(2,name),(70,0),(62,color),(6,'CONTINUOUS')]: tag(code,value)
    tag(0,'ENDTAB'); tag(0,'ENDSEC'); tag(0,'SECTION'); tag(2,'BLOCKS')
    block('ELA_BOX',[(-10,-40),(10,-40),(10,40),(-10,40)])
    for name in ['ELA_LAMP','ELA_SIGN']:
        block(name,[(-2,-2),(2,-2),(2,2),(-2,2)])
    tag(0,'ENDSEC'); tag(0,'SECTION'); tag(2,'ENTITIES')
    insert('ELA_BOX','ELA_PANEL',(100,100))
    line('ELA_WIRE',(110,80),(150,80)); insert('ELA_LAMP','ELA_DEVICE',(152,80))
    polyline('ELA_WIRE',[(154,80),(157,80),(160,80)])
    line('ELA_WIRE',(180,80),(200,80)); insert('ELA_LAMP','ELA_DEVICE',(202,80))
    line('ELA_WIRE',(170,70),(170,90))  # Independent crossing; two unrelated bare ends.
    polyline('ELA_WIRE',[(110,100),(130,100),(150,100)])
    insert('ELA_SIGN','ELA_DEVICE',(152,100))
    line('ELA_WIRE',(154,100),(200,100)); insert('ELA_SIGN','ELA_DEVICE',(202,100))
    line('ELA_WIRE',(110,120),(150,120)); insert('ELA_LAMP','ELA_DEVICE',(152,120))
    tag(0,'ENDSEC'); tag(0,'EOF')
    return '\n'.join(rows)+'\n'


EXPECTED = {
    'version': 1,
    'kind': 'synthetic CAD fixture; not imported or validated in AutoCAD here',
    'units': 'mm for this synthetic fixture only',
    'panel': {'name':'ELA_BOX','insertion':[100,100,0]},
    'layers': {'panel':'ELA_PANEL','wire':'ELA_WIRE','device':'ELA_DEVICE'},
    'circuits': [
        {'seed':[110,80,0], 'devices':{'ELA_LAMP':2}, 'watts_after_category_confirmation':10},
        {'seed':[110,100,0], 'devices':{'ELA_SIGN':2}, 'watts_after_category_confirmation':2},
        {'seed':[110,120,0], 'devices':{'ELA_LAMP':1}, 'watts_after_category_confirmation':5},
    ],
    'box_watts_after_category_confirmation':17,
    'gap': [[160,80,0],[180,80,0]],
    'unrelated_crossing': [[170,70,0],[170,90,0]],
    'dynamic_templates': 'not provided',
}


if __name__ == '__main__':
    destination = Path(__file__).resolve().parent
    (destination/'cad-plan.dxf').write_text(build_dxf(),encoding='ascii')
    (destination/'cad-plan.expected.json').write_text(json.dumps(EXPECTED,indent=2)+'\n')
