import sys
from extract_tex import toc, find

cands = [
    "materialgraph/ui/material_textures/sargasso_map_uv.texture",
    "ui/material_textures/sargasso_map_uv.texture",
    "material_textures/sargasso_map_uv.texture",
    "textures/ui/material_textures/sargasso_map_uv.texture",
    "materialgraph/ui/Material_Textures/sargasso_map_UV_6-17-2021.texture",
    "ui/Material_Textures/sargasso_map_UV_6-17-2021.texture",
    "models/ui/Map_ardolis/Map_ardolis.model",
    "models/ui/Map_sargasso/Map_sargasso.model",
    "material/ui/map_01/gbl_map_01.material",
    "material/ui/map_sargasso_bg/map_sargasso_bg.material",
    "material/ui/levelmap_base/levelmap_base.material",
    "ui/loaded/authored/_art/textures/mapicongoldbolt.texture",
] + sys.argv[1:]
t = toc()
for c in cands:
    e = find(c)
    print(f"{len(e)}  {c}" + (f"   sizes={[x.size for x in e]}" if e else ""))
