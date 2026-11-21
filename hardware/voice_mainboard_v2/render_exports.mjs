// Raster previews of generated SVGs; schematic SVG remains the zoomable source.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

const root=path.dirname(fileURLToPath(import.meta.url));
const workspace=path.resolve(root,'../..');
const require=createRequire(path.join(workspace,'build/svg-render/package.json'));
const {Resvg}=require('@resvg/resvg-js');
for(const [relative,width] of [['overview.svg',1560],['schematic/voice_mainboard_v2.svg',3200]]){
  const source=path.join(root,'exports',relative);
  const target=source.replace(/\.svg$/,'.png');
  const image=new Resvg(fs.readFileSync(source),{
    font:{loadSystemFonts:true,defaultFontFamily:'Microsoft YaHei'},
    fitTo:{mode:'width',value:width},
  }).render();
  fs.writeFileSync(target,image.asPng());
  console.log(`${relative}: ${image.width}x${image.height}`);
}
