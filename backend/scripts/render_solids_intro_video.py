"""Render an original, silent observation clip; no borrowed textbook artwork."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw


def rotation(yaw, pitch=0):
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    return np.array([[cy, sy * sp, sy * cp], [0, cp, -sp], [-sy, cy * sp, cy * cp]])


def mesh(kind):
    if kind in ('box', 'cube'):
        sx, sy, sz = (1.05, .5, .65) if kind == 'box' else (.65, .65, .65)
        vertices = np.array([(x*sx, y*sy, z*sz) for x, y, z in
                            [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                             (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]])
        return vertices, [(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)]
    vertices, faces = [], []
    rows, columns = (16, 32) if kind == 'ball' else (2, 48)
    for row in range(rows + 1):
        for col in range(columns):
            angle = col * math.tau / columns
            if kind == 'ball':
                latitude = row * math.pi / rows
                vertices.append((math.sin(latitude)*math.cos(angle)*.78,
                                 math.cos(latitude)*.78,
                                 math.sin(latitude)*math.sin(angle)*.78))
            else:
                vertices.append((math.cos(angle)*.55, .88-row*.88, math.sin(angle)*.55))
    for row in range(rows):
        for col in range(columns):
            nxt = (col+1) % columns
            faces.append((row*columns+col,row*columns+nxt,(row+1)*columns+nxt,(row+1)*columns+col))
    if kind == 'can':
        faces.extend([tuple(range(columns-1,-1,-1)),tuple(range(rows*columns,(rows+1)*columns))])
    return np.array(vertices), faces


def frame(t, width=960, height=540):
    image = Image.new('RGB', (width, height), '#f4ead8')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((54, 25, 405, 240), radius=20, fill='#d5e7e5', outline='#fff9ef', width=12)
    draw.line((230, 31, 230, 237), fill='#fff9ef', width=10)
    draw.line((58, 130, 399, 130), fill='#fff9ef', width=10)
    draw.ellipse((84, 174, 200, 281), fill='#9fbc83')
    draw.rounded_rectangle((118, 237, 166, 310), radius=6, fill='#b47856')
    draw.rectangle((0, 344, width, height), fill='#d9b78a')
    draw.polygon([(80,310),(880,310),(960,420),(0,420)], fill='#e6c79f')
    draw.line((0,420,960,420), fill='#ba9368', width=5)
    view = rotation(.35, -.26)
    specifications = [('box',245,362,52,(201,139,67)),('cube',416,357,57,(133,116,180)),
                      ('can',594,350,57,(58,143,137)),('ball',769,366,60,(224,112,67))]
    for index,(kind,cx,cy,scale,base) in enumerate(specifications):
        active = 2 <= t < 10 and int((t-2)//2) == 3-index
        phase = (t-2) % 2
        yaw = .2 + (.7*math.sin(phase*math.pi) if active else 0)
        pitch = (.9*math.sin(phase*math.pi) if active and kind == 'can' else 0)
        if active and kind == 'ball':
            cx += 28*math.sin(phase*math.pi)
        if active:
            draw.ellipse((cx-95,cy+42,cx+95,cy+72),fill='#bd976f')
        else:
            draw.ellipse((cx-67,cy+42,cx+67,cy+64),fill='#c9a77e')
        vertices, faces = mesh(kind)
        local = vertices @ rotation(yaw,pitch).T
        world = local @ view.T
        polygons=[]
        for number,face in enumerate(faces):
            points = world[list(face)]
            normal = np.cross(points[1]-points[0],points[2]-points[0])
            length = np.linalg.norm(normal)
            if length < .000001:
                continue
            normal /= length
            shade = .6 + .35*abs(float(np.dot(normal, np.array([-.4,.65,-.65]))))
            color = base
            if kind == 'ball' and (number % 32)//8 % 2 == 0:
                color=(249,202,112)
            if kind == 'can' and len(face)>4:
                color=(202,215,206)
            color=tuple(int(min(255,c*shade)) for c in color)
            projected=[(cx+float(p[0])*scale,cy-float(p[1])*scale) for p in points]
            polygons.append((float(points[:,2].mean()),projected,color))
        for _,points,color in sorted(polygons,reverse=True):
            draw.polygon(points,fill=color)
        if kind == 'box':
            draw.line((cx-45,cy-8,cx+43,cy-20),fill='#e9c58c',width=6)
    return image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():
        raise SystemExit('Refuse to overwrite an existing media artifact')
    duration,fps=12,20
    command=['ffmpeg','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
             '-s','960x540','-r',str(fps),'-i','-','-an','-c:v','libx264',
             '-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-movflags','+faststart',str(args.output)]
    process=subprocess.Popen(command,stdin=subprocess.PIPE)
    for number in range(duration*fps):
        process.stdin.write(frame(number/fps).tobytes())
    process.stdin.close()
    if process.wait():
        raise SystemExit('Video encoding failed')
    receipt={'schemaVersion':'mira.original-observation-video.v1','kind':'original_rendered_animation',
             'subject':'math','gradeCode':'primary_1','durationSeconds':duration,'fps':fps,
             'dimensions':[960,540],'audio':'separate_prerecorded_teacher',
             'objects':['rectangular_box','cube','cylindrical_can','ball'],
             'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
             'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'publicationAllowed':False}
    args.output.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    frame(6).save(args.output.with_suffix('.poster.png'))
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':
    main()
