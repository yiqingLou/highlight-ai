"""Tile frames into contact sheets, cropping the center-top kill-banner area
so kill frames are easy to spot. Outputs grids of ~150 frames each."""
import glob, os
from PIL import Image, ImageDraw

frames = sorted(glob.glob("datasets/naraka/frames/scan_self/s_*.jpg"))
os.makedirs("grids", exist_ok=True)

cols, per_sheet = 15, 150
thumb = (150, 70)  # crop is wide/short (banner strip)
sheet_idx = 0
for start in range(0, len(frames), per_sheet):
    batch = frames[start:start + per_sheet]
    rows = (len(batch) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb[0], rows * thumb[1]), (15, 15, 15))
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(batch):
        im = Image.open(f)
        w, h = im.size
        # center-top kill-banner strip
        crop = im.crop((int(w*0.30), int(h*0.05), int(w*0.70), int(h*0.22)))
        crop = crop.resize((thumb[0], thumb[1]-12))
        r, c = divmod(i, cols)
        sheet.paste(crop, (c*thumb[0], r*thumb[1]))
        # frame number label
        fn = os.path.basename(f).replace("s_","").replace(".jpg","")
        d.text((c*thumb[0]+2, r*thumb[1]+thumb[1]-11), fn, fill=(255,255,0))
    sheet.save(f"grids/grid_{sheet_idx:02d}.jpg", quality=82)
    sheet_idx += 1
    print(f"grid_{sheet_idx-1:02d}: frames {start+1}-{start+len(batch)}")
print("done,", sheet_idx, "grids")