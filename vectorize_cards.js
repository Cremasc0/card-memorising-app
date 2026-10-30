const fs = require('fs');
const path = require('path');
const PNG = require('pngjs').PNG;
const ImageTracer = require('imagetracerjs');

const project = __dirname;
const suits = ['Bastoni', 'Coppa', 'Dinari', 'Spada'];

for (const suit of suits) {
  const sourceDir = path.join(project, 'work', 'vector-input', suit);
  const outputDir = path.join(project, 'Trevisane Vectors', suit);
  fs.mkdirSync(outputDir, { recursive: true });

  for (let card = 1; card <= 10; card++) {
    const rank = String(card).padStart(2, '0');
    const name = suit + '_' + rank;
    const pngPath = path.join(sourceDir, name + '.png');
    const reviewedCropPath = path.join(project, 'Trevisane Crops', suit, name + '.png');
    const svgPath = path.join(outputDir, name + '.svg');
    const png = PNG.sync.read(fs.readFileSync(pngPath));
    const traced = ImageTracer.imagedataToSVG(
      { width: png.width, height: png.height, data: png.data },
      {
        ltres: 1.2,
        qtres: 1.4,
        pathomit: 16,
        rightangleenhance: true,
        colorsampling: 2,
        numberofcolors: 32,
        mincolorratio: 0,
        colorquantcycles: 2,
        layering: 1,
        strokewidth: 0,
        linefilter: true,
        blurradius: 1,
        blurdelta: 24,
        scale: 1,
        roundcoords: 2,
        viewbox: true,
      },
    );
    const root =
      '<svg xmlns="http://www.w3.org/2000/svg" width="51mm" height="103mm" viewBox="0 0 ' +
      png.width + ' ' + png.height + '">';
    const svg = traced.replace(/^<svg[^>]*>/, root + '<title>' + suit + ' ' + rank + '</title>');

    // Keep the reviewed crop as the PNG alongside its traced SVG.
    fs.copyFileSync(reviewedCropPath, path.join(outputDir, name + '.png'));
    fs.writeFileSync(svgPath, svg);
    console.log(name + ': ' + (Buffer.byteLength(svg) / 1024 / 1024).toFixed(2) + ' MB SVG');
  }
}
