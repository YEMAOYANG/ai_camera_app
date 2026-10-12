"""Concrete, articulated geometry adapters; no generic model fallback.

Stable local renderer families extracted from prior original authors, whose
source SHAs are retained for lineage. No task IDs, Provider or output imports.
"""
from html import escape
from content import textbook_activity_templates as shared

TEMPLATE_ORIGINS = {'mesh': 'f03c980be368a08d908f087800df74f574b09cbecde495616393801009301759', 'book': '4906aace621bd273e448beb3c189ff6e13bc226948a3c56813fb5b5821090e84', 'art': '64e5213f5fbedb2defc19ea4d5b7cb130020b940b02b00a81e1e7c728cd887bc', 'traffic': 'accfecc6d37c971aa0dc2d6276477effcfed841b5015b63bc50098a718fc7485'}

def art(label, body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 128" role="img" aria-label="'
            + escape(label, quote=True) + '"><title>' + escape(label) + '</title>'
            '<rect x="1" y="1" width="158" height="126" rx="16" fill="#fcf6e9"/>' + body + '</svg>')


def grid(rows, cols):
    return ''.join(f'<rect x="{25+x*24}" y="{25+y*25}" width="19" height="19" rx="3" fill="#87a9a2" stroke="#50776f" stroke-width="2"/>'
                   for y in range(rows) for x in range(cols))


def angle(degrees):
    return ('<circle cx="40" cy="94" r="6" fill="#ac8858"/><path d="M40 94h99" stroke="#507f8d" stroke-width="9" stroke-linecap="round"/>'
            f'<path d="M40 94h91" transform="rotate({-degrees} 40 94)" stroke="#ca9a66" stroke-width="9" stroke-linecap="round"/>')


def bag(color='#a7706c', opened=False):
    return ('<path d="M40 40Q80 17 120 40v73H40Z" fill="'+color+'" stroke="#665e51" stroke-width="4"/>'
            '<path d="M59 31V18h42v13M35 50q-20 25 0 50m90-50q20 25 0 50" fill="none" stroke="#665e51" stroke-width="5"/>'
            '<path d="M53 76h54v28H53Z" fill="#e3cda3" stroke="#665e51" stroke-width="3"/>'
            + ('<ellipse cx="80" cy="40" rx="38" ry="15" fill="#574e43" stroke="#c7ad7f" stroke-width="5"/>' if opened else '<path d="M47 47h66" stroke="#e3cda3" stroke-width="5"/>'))


CHILD = '<circle cx="80" cy="29" r="17" fill="#d8b78e"/><path d="M62 48h36v38H62Z" fill="#7097a4"/><path d="M60 54 40 76m60-22 20 22M69 87l-7 29m29-29 7 29" fill="none" stroke="#7097a4" stroke-width="10" stroke-linecap="round"/><circle cx="73" cy="27" r="2"/><circle cx="87" cy="27" r="2"/><path d="M73 36q7 5 14 0" fill="none" stroke="#966d52" stroke-width="2"/>'


BOOK = '<path d="M17 31q32-14 63 0 31-14 63 0v72q-31-14-63 0-31-14-63 0Z" fill="#e9dbb6" stroke="#8b7956" stroke-width="4"/><path d="M80 31v72" stroke="#8b7956" stroke-width="3"/>'


def shape(key):
    if key.startswith('abacus'):
        count=int(key[-1]);return '<rect x="13" y="32" width="134" height="64" rx="7" fill="none" stroke="#9b7754" stroke-width="9"/><path d="M17 64h126" stroke="#8d9a91" stroke-width="5"/>'+''.join(f'<ellipse cx="{28+i*24}" cy="64" rx="9" ry="18" fill="'+('#b57569' if i<count else '#c9d4bf')+'" stroke="#8b735b" stroke-width="2"/>' for i in range(5))
    if key.startswith('array'):
        return grid(*{'array23':(2,3),'array24':(2,4),'array42':(4,2)}[key])
    if key.startswith('angle'):
        return angle(int(key[5:]))
    if key.startswith('bag'):
        return bag({'bagred':'#b7776d','bagblue':'#709daf','bagyellow':'#c9aa5f'}.get(key,'#b7776d'),key=='bagopen')
    if key=='cylinder':return '<path d="M40 35v63q40 27 80 0V35" fill="#85abb0" stroke="#537e88" stroke-width="4"/><ellipse cx="80" cy="35" rx="40" ry="16" fill="#c0d7d4" stroke="#537e88" stroke-width="4"/><path d="M40 98q40 27 80 0" fill="none" stroke="#537e88" stroke-width="4"/>'
    if key=='cone':return '<path d="m80 13-49 92q49 29 98 0Z" fill="#d1ac72" stroke="#9d7951" stroke-width="4"/><ellipse cx="80" cy="105" rx="49" ry="13" fill="#ead2a4" stroke="#9d7951" stroke-width="3"/>'
    if key=='solid_pair':return '<g transform="translate(-7 24) scale(.7)">'+shape('cylinder')+'</g><g transform="translate(65 26) scale(.7)">'+shape('cone')+'</g>'
    if key=='scissors':return '<ellipse cx="43" cy="94" rx="17" ry="12" transform="rotate(-30 43 94)" fill="none" stroke="#779c9e" stroke-width="9"/><ellipse cx="112" cy="94" rx="17" ry="12" transform="rotate(30 112 94)" fill="none" stroke="#779c9e" stroke-width="9"/><path d="m55 83 56-63q9-8 10 2L66 83m36 0L46 20q-9-8-10 2l55 61" fill="#c8d0c8" stroke="#77867e" stroke-width="3"/><circle cx="79" cy="65" r="6" fill="#b38d5b"/>'
    if key=='spoon':return '<ellipse cx="80" cy="34" rx="22" ry="27" fill="#b6c5c2" stroke="#6d8a8a" stroke-width="4"/><path d="M80 58v52" stroke="#8ca6a5" stroke-width="12" stroke-linecap="round"/>'
    if key=='magnet':return '<path d="M37 34v46a43 37 0 0 0 86 0V34h-24v46a19 14 0 0 1-38 0V34Z" fill="#a56f69" stroke="#795a53" stroke-width="3"/><path d="M37 34h24v21H37Zm62 0h24v21H99Z" fill="#a8c2c7" stroke="#65858b" stroke-width="2"/>'
    if key in ('circuit','switch_open','switch_closed'):
        return '<path d="M24 94V48h47m30 0h34v46H24Z" fill="none" stroke="#799d88" stroke-width="6"/><rect x="17" y="68" width="14" height="29" fill="#c4a46c"/><circle cx="134" cy="48" r="17" fill="#e7cf83" stroke="#a68d50" stroke-width="3"/><path d="M71 48l28 '+('0' if key=='switch_closed' else '-20')+'" stroke="#9a7b55" stroke-width="6"/><circle cx="71" cy="48" r="5" fill="#77776b"/>'
    if key in ('lever','lever_left','lever_right'):
        d={'lever':0,'lever_left':-18,'lever_right':18}[key];return '<path d="m80 63-21 48h42Z" fill="#ba9a6c" stroke="#8a704b" stroke-width="3"/><g transform="rotate('+str(d)+' 80 61)"><path d="M16 61h128" stroke="#77959b" stroke-width="12"/><rect x="25" y="37" width="22" height="19" fill="#b8786c"/><rect x="115" y="37" width="22" height="19" fill="#9bb57d"/></g>'
    if key.startswith('bridge'):
        body='<path d="M12 110q35-13 68 0t68 0" fill="none" stroke="#8fb9bd" stroke-width="12"/><path d="M15 79h130M30 79v25m100-25v25" stroke="#a08b66" stroke-width="9"/>'
        if key=='bridge_arch':body+='<path d="M29 99q51-84 102 0" fill="none" stroke="#8e9d8a" stroke-width="10"/>'
        if key=='bridge_truss':body+='<path d="m20 77 20-36 20 36 20-36 20 36 20-36 20 36M40 41h80" fill="none" stroke="#70999f" stroke-width="5"/>'
        return body
    if key.startswith('bus'):
        door='<path d="M108 47h23v47h-23Z" fill="#b6d6d2" stroke="#60848b" stroke-width="3"/>'
        return '<rect x="13" y="37" width="133" height="63" rx="12" fill="#c3a96e" stroke="#8c7953" stroke-width="3"/><path d="M24 47h24v24H24Zm34 0h24v24H58Zm34 0h11v24H92Z" fill="#b6d6d2" stroke="#60848b" stroke-width="2"/>'+door+'<circle cx="40" cy="101" r="15" fill="#5b726e"/><circle cx="119" cy="101" r="15" fill="#5b726e"/>'+('<path d="M111 48l23-8v57l-23-8Z" fill="#86a9aa" stroke="#60848b" stroke-width="3"/>' if key=='busdoor' else '')
    if key.startswith('cabinet'):
        return '<path d="M27 20h106v96H27Z" fill="#cdb58a" stroke="#8d7656" stroke-width="4"/><path d="M32 69h96" stroke="#8d7656" stroke-width="5"/>'+('<path d="M31 24h97v41H31Z" fill="#d9c7a4" stroke="#8d7656" stroke-width="3"/><circle cx="117" cy="45" r="3" fill="#8d7656"/>' if key=='cabinet_closed' else '<path d="m31 24-19 9v38l19-7Z" fill="#d9c7a4" stroke="#8d7656" stroke-width="3"/><path d="M46 46h24v17H46Z" fill="#87a9a6"/><path d="M70 48q14 0 7 12h-7" fill="none" stroke="#87a9a6" stroke-width="4"/>')+('<path d="m33 82 15-9h67l15 9-15 23H48Z" fill="#ae956e" stroke="#8d7656" stroke-width="3"/>' if key=='cabinet_drawer' else '')
    if key=='bicycle':return '<circle cx="40" cy="91" r="28" fill="none" stroke="#648487" stroke-width="6"/><circle cx="120" cy="91" r="28" fill="none" stroke="#648487" stroke-width="6"/><path d="m40 91 28-48 22 48H40l47-44 33 44m-33-44 7-16h13M59 42h24" fill="none" stroke="#b38a5a" stroke-width="5" stroke-linecap="round"/><circle cx="90" cy="91" r="8" fill="#7e8f80"/>'
    if key=='ruler':return '<rect x="15" y="43" width="130" height="38" fill="#e0c58e" stroke="#998153" stroke-width="3"/>'+''.join(f'<path d="M{20+i*12} 43v{20 if i%2==0 else 11}" stroke="#8d7954" stroke-width="2"/>' for i in range(11))
    if key=='parallelogram':return '<path d="m44 27 96 0-24 77H20Z" fill="#94b4aa" stroke="#5b877d" stroke-width="4"/>'
    if key=='trapezoid':return '<path d="M49 27h62l34 77H15Z" fill="#d1ad79" stroke="#9b7c50" stroke-width="4"/>'
    if key=='star':return '<path d="m80 13 16 34 38 5-28 28 7 39-33-19-33 19 7-39-28-28 38-5Z" fill="#d4b66b" stroke="#a78b4f" stroke-width="4"/>'
    if key=='family':return '<g transform="translate(-3 21) scale(.7)">'+CHILD+'</g><g transform="translate(70 11) scale(.8)">'+CHILD.replace('#7097a4','#a98e79')+'</g>'
    if key=='friends':return '<g transform="translate(-7 13) scale(.75)">'+CHILD+'</g><g transform="translate(70 13) scale(.75)">'+CHILD.replace('#7097a4','#9eac79')+'</g><path d="M66 68h24" stroke="#d8b78e" stroke-width="7"/>'
    if key=='walk':return CHILD+'<path d="M17 122h125m-93-10 13-19m36 17 10-18" fill="none" stroke="#b19b75" stroke-width="4"/>'
    if key=='clock':return '<circle cx="80" cy="63" r="48" fill="#eef0df" stroke="#78949c" stroke-width="6"/>'+''.join(f'<path d="M80 19v9" transform="rotate({i*30} 80 63)" stroke="#78949c" stroke-width="3"/>' for i in range(12))+'<path d="M80 63V30m0 33 24 16" stroke="#a28055" stroke-width="5" stroke-linecap="round"/>'
    if key=='shirt':return '<path d="m60 20-36 20 15 29 18-12v61h47V57l18 12 15-29-36-20q-21 22-41 0Z" fill="#8aafac" stroke="#597f7c" stroke-width="4"/><path d="M63 22q18 31 35 0" fill="none" stroke="#597f7c" stroke-width="4"/>'
    if key=='suitcase':return '<rect x="28" y="42" width="105" height="70" rx="9" fill="#a2b697" stroke="#6b805f" stroke-width="4"/><path d="M61 42V24h39v18m-52 0v70m65-70v70" fill="none" stroke="#6b805f" stroke-width="5"/><circle cx="47" cy="117" r="5" fill="#6b805f"/><circle cx="115" cy="117" r="5" fill="#6b805f"/>'
    if key=='stools':return '<path d="M22 65h48v12H22Zm8 12-4 36m36-36 4 36M91 37h48v12H91Zm8 12-4 64m36-64 4 64" fill="#c9ac7c" stroke="#8c7652" stroke-width="4"/>'
    if key=='crosswalk':return '<path d="M6 29h148v76H6Z" fill="#aeb5aa"/>'+''.join(f'<path d="M{20+i*25} 38h15v58H{20+i*25}Z" fill="#f4f1dd"/>' for i in range(5))+'<circle cx="125" cy="14" r="9" fill="#82a580"/>'
    if key=='breakfast':return '<ellipse cx="80" cy="84" rx="62" ry="27" fill="#e0e4cc" stroke="#8e9d80" stroke-width="3"/><ellipse cx="57" cy="74" rx="27" ry="19" fill="#eed3a2" stroke="#ba9968" stroke-width="3"/><path d="M100 31h26v49h-26Z" fill="#bfd9d2" stroke="#6b9697" stroke-width="3"/><path d="M126 38q20 0 12 23h-12" fill="none" stroke="#6b9697" stroke-width="4"/>'
    if key=='school':return '<path d="M27 50h106v65H27Z" fill="#d5ba88" stroke="#8d7956" stroke-width="3"/><path d="m17 50 63-37 65 37Z" fill="#b58069"/><path d="M66 80h28v35H66Z" fill="#7c9a9c"/><path d="M37 62h18v16H37Zm70 0h18v16h-18Z" fill="#b9dbe0"/>'
    if key=='light':return '<path d="M48 22h40l36 24-36 24H48Z" fill="#a0b7a7" stroke="#6d8b79" stroke-width="4"/><path d="m124 46 25-22v44Z" fill="#edda96"/><path d="M52 34h17" stroke="#e9e1bf" stroke-width="4"/>'
    if key=='pulley':return '<path d="M20 18h120" stroke="#97825d" stroke-width="8"/><circle cx="80" cy="52" r="25" fill="#a8b7a4" stroke="#6e8877" stroke-width="5"/><path d="M80 18v12M55 52v57m50-57v39" stroke="#ad8c5f" stroke-width="4"/><path d="M37 108h36v17H37Zm53-17h30v23H90Z" fill="#c9aa75" stroke="#8e7653" stroke-width="3"/>'
    if key=='rocks':return '<path d="m13 93 15-32 32-5 18 25-20 29H28Z" fill="#a8b2a0" stroke="#737f6b" stroke-width="3"/><path d="m88 102-12-28 26-40 29 8 17 49-24 21Z" fill="#c4b295" stroke="#8f7d62" stroke-width="3"/>'
    if key=='cloud':return '<path d="M23 85q-22-29 12-42 9-35 43-18 29-16 43 13 32 1 28 31-5 20-32 20H40Z" fill="#d7e6e4" stroke="#90aeb1" stroke-width="4"/>'
    if key=='moon':return '<circle cx="80" cy="62" r="46" fill="#d9d6b2" stroke="#aaa87f" stroke-width="3"/><circle cx="61" cy="48" r="9" fill="#babd9e"/><circle cx="97" cy="75" r="13" fill="#babd9e"/><circle cx="58" cy="88" r="7" fill="#babd9e"/>'
    if key=='fish':return '<ellipse cx="74" cy="66" rx="45" ry="27" fill="#83aeb4" stroke="#56818c" stroke-width="3"/><path d="m116 65 30-26v52Z" fill="#9ebda8" stroke="#56818c" stroke-width="3"/><circle cx="45" cy="60" r="4" fill="#405f60"/><path d="m70 43 15-20 15 25" fill="#9ebda8"/>'
    if key=='cup':return '<path d="M38 31h65v65q-32 23-65 0Z" fill="#b4d1c8" stroke="#628a83" stroke-width="4"/><ellipse cx="70" cy="31" rx="33" ry="11" fill="#dfeae0" stroke="#628a83" stroke-width="4"/><path d="M105 47q46-12 29 36-11 13-31 0" fill="none" stroke="#628a83" stroke-width="9"/>'
    if key=='hammer':return '<path d="m71 43 19 5-17 71-19-5Z" fill="#b59768" stroke="#826c4c" stroke-width="3"/><path d="m47 24 59 13 16 25-30-6-8-15-7 23-34-9Z" fill="#94a8a0" stroke="#647f75" stroke-width="3"/>'
    if key=='leaf':return '<path d="M79 112Q14 83 42 29q63-32 85-13 18 73-48 96Z" fill="#93ae75" stroke="#607f50" stroke-width="3"/><path d="M76 119 110 28M93 79 54 58m47 2-17-23" fill="none" stroke="#607f50" stroke-width="3"/>'
    if key=='cart':return '<rect x="25" y="38" width="109" height="61" rx="6" fill="#9eafa1" stroke="#6c8274" stroke-width="3"/><circle cx="45" cy="101" r="15" fill="#657d7e"/><circle cx="116" cy="101" r="15" fill="#657d7e"/>'
    if key=='bars':return '<path d="M18 15v99h128" fill="none" stroke="#8a9b88" stroke-width="4"/><path d="M35 68h21v41H35Zm39-30h21v71H74Zm39 15h21v56h-21Z" fill="#8aacaa" stroke="#608583" stroke-width="3"/>'
    if key=='tiles':return grid(3,4)
    if key=='map':return '<path d="m14 24 43-8 49 13 39-9v85l-39 9-49-13-43 9Z" fill="#c8d5ac" stroke="#879973" stroke-width="3"/><path d="m30 92 25-55 49 49 28-47" fill="none" stroke="#aa8860" stroke-width="7"/><circle cx="132" cy="39" r="8" fill="#b77969"/>'
    if key=='blocks':return '<path d="m19 74 26-14 28 14-28 16Zm0 0v27l26 15V90m0 0 28-16v27l-28 15M83 49l26-14 28 14-28 16Zm0 0v52l26 15V65m0 0 28-16v52l-28 15" fill="#d0ac77" stroke="#8f714b" stroke-width="3"/>'
    if key=='book':return BOOK
    if key=='song':return BOOK+'<path d="M45 47v31m0-29 20-6v29" fill="none" stroke="#70939a" stroke-width="5"/><ellipse cx="40" cy="80" rx="9" ry="6" fill="#70939a"/><ellipse cx="60" cy="74" rx="9" ry="6" fill="#70939a"/>'
    if key=='wordcards':return '<g fill="#d9c6a0" stroke="#8f7e5a" stroke-width="3"><rect x="21" y="18" width="67" height="41" rx="5"/><rect x="68" y="49" width="67" height="41" rx="5"/><rect x="26" y="80" width="67" height="36" rx="5"/></g><path d="M33 30h40m-40 11h28m49 21h40m-40 11h27m-63 21h40" stroke="#b69a70" stroke-width="4"/>'
    if key=='dictionary':return '<path d="M35 18h89v97H35Z" fill="#9db6a5" stroke="#698775" stroke-width="4"/><path d="M35 26H24v97h91v-8M43 18v97" fill="none" stroke="#698775" stroke-width="4"/><path d="M124 34h12v13h-12m0 13h12v13h-12m0 13h12v13h-12" fill="#d1b275"/>'
    if key=='speech':return '<path d="M18 24h124v60H69l-31 24V84H18Z" fill="#d5e1cc" stroke="#849a7c" stroke-width="4"/><path d="M37 43h87m-87 20h56" stroke="#9bb18e" stroke-width="5"/>'
    if key=='play':return '<path d="M15 18h130v101H15Z" fill="#d5b58c" stroke="#997853" stroke-width="3"/><path d="M15 18q20 34 0 73m130-73q-20 34 0 73" fill="#ac7a6b"/><g transform="translate(40 30) scale(.5)">'+CHILD+'</g>'
    if key=='soundbook':return BOOK+'<path d="M43 56h9l13-12v43L52 75h-9Zm33-5q12 15 0 29m8-35q20 21 0 41" fill="none" stroke="#71969e" stroke-width="4"/>'
    if key=='chairball':return '<path d="M30 49h55v34H30Zm6-34h43v34H36ZM37 83v34m41-34v34" fill="#bfa373" stroke="#8e7551" stroke-width="4"/><circle cx="120" cy="98" r="21" fill="#91acb2" stroke="#63818b" stroke-width="3"/>'
    if key=='shopping':return '<path d="M25 34h30l15 61h64l16-43H61" fill="none" stroke="#7a9284" stroke-width="6"/><circle cx="82" cy="111" r="9" fill="#8b9e8a"/><circle cx="126" cy="111" r="9" fill="#8b9e8a"/><rect x="80" y="29" width="23" height="35" fill="#caa973"/><circle cx="122" cy="54" r="16" fill="#ae806b"/>'
    raise ValueError('no_generic_picture_fallback:'+key)


def svg(label, shapes):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 128" role="img" aria-label="{escape(label)}">'
            f'<title>{escape(label)}</title><rect width="160" height="128" rx="16" fill="#fcf6e9"/>{shapes}</svg>')


def legacy_model_pictures(adapter):
    boat = '<path d="m22 70 31 31h54l31-31-58 14Z" fill="#c68f55" stroke="#80623e" stroke-width="3"/><path d="m46 73 34-39 34 39-34 11Z" fill="#f1d1a0" stroke="#9d794e" stroke-width="3"/><path d="M80 34v50" stroke="#9d794e" stroke-width="3"/>'
    if adapter == 'chinese_paper_boat_and_kite':
        return [svg('移近观察折纸船', boat),
                svg('转到另一边观察纸船', '<g transform="translate(160 0) scale(-1 1)">' + boat + '</g><path d="m30 30 18-9 4 17" fill="none" stroke="#568d88" stroke-width="5"/>'),
                svg('提起风筝观察连着的绳子', '<path d="m80 10 37 38-37 38-37-38Z" fill="#7fa5b7" stroke="#4e7383" stroke-width="3"/><path d="M80 10v76M43 48h74" stroke="#bd925c" stroke-width="3"/><path d="M80 86q-30 15 8 30" fill="none" stroke="#866f56" stroke-width="3"/>')]
    if adapter == 'chinese_bird_boat_bowl':
        bird = '<ellipse cx="68" cy="67" rx="34" ry="23" fill="#75a0ac"/><circle cx="103" cy="45" r="18" fill="#75a0ac"/><path d="m118 44 20 7-20 5M39 65 20 48l3 28" fill="#d1a355"/><ellipse cx="67" cy="65" rx="22" ry="11" fill="#a6c5cc"/><circle cx="109" cy="40" r="3" fill="#294744"/><path d="m62 89-5 20m22-20 4 20" stroke="#967347" stroke-width="4"/>'
        return [svg('移近小鸟观察翅膀', bird),
                svg('转动观察另一侧翅膀', '<g transform="translate(160 0) scale(-1 1)">' + bird + '</g><path d="m40 23 18-8 4 16" fill="none" stroke="#568d88" stroke-width="5"/>'),
                svg('碗与小船并排观察轮廓', '<g transform="translate(-7 28) scale(.6)">' + boat + '</g><path d="M91 68q22 66 48 0Z" fill="#b6c9ac" stroke="#71917c" stroke-width="3"/><ellipse cx="115" cy="68" rx="24" ry="9" fill="#e2eadc" stroke="#71917c" stroke-width="3"/>')]
    if adapter == 'english_coloured_spheres_and_tray':
        pictures = [svg(label, f'<ellipse cx="80" cy="103" rx="48" ry="10" fill="#dfd2b2"/><circle cx="80" cy="58" r="31" fill="{color}"/><ellipse cx="70" cy="46" rx="10" ry="7" fill="#fff5dd" opacity=".6"/>')
                    for label, color in [('把红色球移进盘子', '#cb6660'), ('把蓝色球移进盘子', '#5b8db9')]]
        pictures.append(svg('三种颜色的球并排观察', '<ellipse cx="80" cy="98" rx="69" ry="15" fill="#dfd2b2"/><circle cx="31" cy="67" r="20" fill="#cb6660"/><circle cx="80" cy="67" r="20" fill="#5b8db9"/><circle cx="129" cy="67" r="20" fill="#d9b74d"/>'))
        return pictures
    if adapter == 'english_hinged_umbrella_mesh':
        handle = '<path d="M80 45v58q0 18-14 11-7-4-6-12" fill="none" stroke="#806749" stroke-width="5"/>'
        return [svg('收拢的伞骨靠近手柄', handle + '<path d="m80 15-12 69 12-5 12 5Z" fill="#78a5ad" stroke="#507c87" stroke-width="3"/><path d="M80 15v63m0-63 12 69m-12-69-12 69" stroke="#cfad75" stroke-width="2"/>'),
                svg('展开的伞面与手柄', handle + '<path d="M22 61Q80-20 138 61L109 54 80 63 51 54Z" fill="#78a5ad" stroke="#507c87" stroke-width="3"/><path d="M80 17 51 54m29-37v46m0-46 29 37" stroke="#cfad75" stroke-width="2"/>'),
                svg('转动展开的伞观察手柄', '<g transform="translate(20 -12) rotate(20 80 70)">' + handle + '<path d="M22 61Q80-20 138 61L109 54 80 63 51 54Z" fill="#78a5ad" stroke="#507c87" stroke-width="3"/><path d="M80 17 51 54m29-37v46m0-46 29 37" stroke="#cfad75" stroke-width="2"/></g>')]
    raise ValueError('unsupported_original_model_picture_adapter')


MESH_BUILDERS = r"""
function polygon(vertices,faces){const out=[];faces.forEach((f,i)=>{for(let k=1;k<f.length-1;k++)triangle(out,vertices[f[0]],vertices[f[k]],vertices[f[k+1]],[1,1,1],.7+(i%5)*.06);});return out;}
function tubeBetween(a,b,r=.018){const d=b.map((x,i)=>x-a[i]),len=Math.hypot(...d),w=d.map(x=>x/len),t=Math.abs(w[1])<.9?[0,1,0]:[1,0,0],u=[w[1]*t[2]-w[2]*t[1],w[2]*t[0]-w[0]*t[2],w[0]*t[1]-w[1]*t[0]],ul=Math.hypot(...u);u.forEach((v,i)=>u[i]=v/ul);const v=[w[1]*u[2]-w[2]*u[1],w[2]*u[0]-w[0]*u[2],w[0]*u[1]-w[1]*u[0]],out=[];for(let k=0;k<8;k++){const p=(c,i)=>c.map((x,j)=>x+r*(u[j]*Math.cos(i*Math.PI/4)+v[j]*Math.sin(i*Math.PI/4)));triangle(out,p(a,k),p(b,k),p(b,k+1),[1,1,1],.85);triangle(out,p(a,k),p(b,k+1),p(a,k+1),[1,1,1],.85);}return out;}
function linePart(group,key,a,b,color,r){geometries[key]=tubeBetween(a,b,r);part(group,key,0,0,0,1,1,1,color);}
function foldedBoat(){return polygon([[-.9,0,0],[-.45,-.28,.35],[.45,-.28,.35],[.9,0,0],[.45,-.28,-.35],[-.45,-.28,-.35],[0,.58,0],[0,.02,.38],[0,.02,-.38]],[[1,2,4,5],[0,1,2,3,7],[3,4,5,0,8],[0,6,7],[6,3,7],[0,8,6],[6,8,3]]);}
function boatHull(){return polygon([[-.85,.15,0],[-.55,-.15,.36],[.55,-.15,.36],[.85,.15,0],[.55,-.15,-.36],[-.55,-.15,-.36],[-.55,.24,.36],[.55,.24,.36],[.55,.24,-.36],[-.55,.24,-.36]],[[1,2,4,5],[0,1,2,3,7,6],[3,4,5,0,9,8],[0,6,9],[3,8,7]]);}
function bowlLathe(){const profile=[[0,0],[.2,0],[.4,.1],[.57,.34],[.65,.61],[.62,.64],[.55,.39],[.38,.19],[.2,.1],[0,.1]],out=[];for(let k=0;k<profile.length-1;k++)for(let i=0;i<32;i++){const p=(j,t)=>[profile[j][0]*Math.cos(t),profile[j][1],profile[j][0]*Math.sin(t)],a=i*Math.PI/16,b=(i+1)*Math.PI/16,l=.7+.22*Math.cos(a-.5);triangle(out,p(k,a),p(k+1,a),p(k+1,b),[1,1,1],l);triangle(out,p(k,a),p(k+1,b),p(k,b),[1,1,1],l);}return out;}
function cone(){const out=[];for(let i=0;i<20;i++){const a=i*Math.PI/10,b=(i+1)*Math.PI/10;triangle(out,[.5,0,0],[-.5,Math.cos(a)*.5,Math.sin(a)*.5],[-.5,Math.cos(b)*.5,Math.sin(b)*.5],[1,1,1],.85);}return out;}
function createScene(){
meshes.length=0;
part('ground','box',0,-.14,0,6,.18,3.2,[.77,.83,.70]);
if(adapter==='chinese_paper_boat_and_kite'){
 geometries.foldedboat=foldedBoat();part('boat','foldedboat',0,.35,0,1,1,1,[.84,.63,.39]);
 geometries.kite=polygon([[0,.55,0],[-.38,0,0],[0,-.55,0],[.38,0,0],[0,0,.08]],[[0,1,4],[1,2,4],[2,3,4],[3,0,4]]);part('kite','kite',0,0,0,1,1,1,[.43,.66,.72]);
 linePart('kite','kiteVertical',[0,-.55,.03],[0,.55,.03],[.67,.48,.27],.014);linePart('kite','kiteHorizontal',[-.38,0,.03],[.38,0,.03],[.67,.48,.27],.014);
 const p=poses.kite;linePart('string','kiteString',[1,.08,.2],[p.x,p.y-.55,p.z],[.52,.43,.31],.009);
}else if(adapter==='chinese_bird_boat_bowl'){
 geometries.hull=boatHull();part('boat','hull',0,.3,0,1,1,1,[.66,.47,.27]);geometries.bowl=bowlLathe();part('bowl','bowl',0,0,0,1,1,1,[.58,.72,.59]);
 part('bird','sphere',0,.78,0,.95,.62,.55,[.38,.59,.67]);part('bird','sphere',.4,1.08,0,.43,.43,.42,[.38,.59,.67]);geometries.beak=cone();part('bird','beak',.68,1.06,0,.3,.2,.2,[.85,.65,.32]);
 const w=wingAngle;part('bird','sphere',-.06,.85,.29,.62,.12,.39,[.65,.78,.80],0,w);part('bird','sphere',-.06,.85,-.29,.62,.12,.39,[.65,.78,.80],0,-w);
 geometries.tail=polygon([[-.35,.70,-.12],[-.8,.93,0],[-.8,.65,0],[-.35,.70,.12]],[[0,1,2],[2,3,0]]);part('bird','tail',0,0,0,1,1,1,[.57,.71,.73]);
 [-.14,.14].forEach(z=>{part('bird','sphere',.48,1.16,z,.07,.07,.07,[.12,.18,.17]);part('bird','cylinder',.05,.34,z,.045,.4,.045,[.52,.40,.27]);});
}else if(adapter==='english_coloured_spheres_and_tray'){
 geometries.tray=bowlLathe();part('tray','tray',0,0,.45,2.8,.36,1.5,[.73,.65,.44]);part('shelf','box',0,.35,-.95,4,.16,.65,[.55,.67,.64]);
 part('red','sphere',0,.45,0,.68,.68,.68,[.78,.32,.29]);part('blue','sphere',0,.45,0,.68,.68,.68,[.27,.50,.73]);part('yellow','sphere',0,.45,0,.68,.68,.68,[.86,.69,.24]);
}else if(adapter==='english_hinged_umbrella_mesh'){
 const radius=1.28*Math.sin(opening),rimY=2.32-1.28*Math.cos(opening),hub=[0,2.32,0];
 const rim=Array.from({length:8},(_,i)=>[radius*Math.cos(i*Math.PI/4),rimY,radius*Math.sin(i*Math.PI/4)]),fabric=[];
 for(let i=0;i<8;i++){triangle(fabric,hub,rim[i],rim[(i+1)%8],[1,1,1],.7+(i%3)*.09);linePart('umbrella','rib'+i,hub,rim[i],[.68,.57,.35],.014);}
 geometries.fabric=fabric;part('umbrella','fabric',0,0,0,1,1,1,[.36,.63,.70]);linePart('umbrella','shaft',[0,.42,0],[0,2.38,0],[.57,.46,.30],.022);
 for(let i=0;i<10;i++){const p=t=>[-.13+.13*Math.cos(t),.42-.13*Math.sin(t),0];linePart('umbrella','hook'+i,p(i*Math.PI/10),p((i+1)*Math.PI/10),[.57,.46,.30],.025);}
}else throw new Error('unsupported-mesh-adapter');
}
"""


ADAPTER_STATES = r"""
function initialPoses(){
 if(adapter==='chinese_paper_boat_and_kite')return {boat:{x:-1,y:0,z:0,angle:0},kite:{x:1,y:.5,z:-.35,angle:0}};
 if(adapter==='chinese_bird_boat_bowl')return {bird:{x:-1.8,y:0,z:-.4,angle:0},boat:{x:0,y:0,z:0,angle:0},bowl:{x:2,y:0,z:-.4,angle:0}};
 if(adapter==='english_coloured_spheres_and_tray')return {red:{x:-1.15,y:.32,z:-.95,angle:0},blue:{x:0,y:.32,z:-.95,angle:0},yellow:{x:1.15,y:.32,z:-.95,angle:0}};
 return {umbrella:{x:0,y:0,z:0,angle:0,tilt:0}};
}
function resetGeometry(){Object.keys(poses).forEach(k=>delete poses[k]);Object.assign(poses,initialPoses());selected=Object.keys(poses)[0];opening=10*Math.PI/180;wingAngle=0;modelState='initial';if(gl){createScene();drawModel();}}
function commitState(id){
 resetGeometry();
 if(adapter==='chinese_paper_boat_and_kite'){
  if(id==='boat_near'||id==='boat_turn'){Object.assign(poses.boat,{x:0,z:1,angle:id==='boat_turn'?Math.PI/2:0});selected='boat';}
  else if(id==='kite_lift'){poses.kite.y=1.5;selected='kite';}else return false;
 }else if(adapter==='chinese_bird_boat_bowl'){
  if(id==='bird_near'||id==='wing_turn'){Object.assign(poses.bird,{x:-.8,z:.65,angle:id==='wing_turn'?Math.PI/2:0});wingAngle=id==='wing_turn'?Math.PI/12:0;selected='bird';}
  else if(id==='bowl_pair'){Object.assign(poses.bowl,{x:1.45,z:.35});poses.bird.x=-2.2;selected='bowl';}else return false;
 }else if(adapter==='english_coloured_spheres_and_tray'){
  if(id==='red'){Object.assign(poses.red,{x:0,y:0,z:.45});selected='red';}
  else if(id==='blue'){Object.assign(poses.blue,{x:0,y:0,z:.45});selected='blue';}
  else if(id==='yellow'){['red','blue','yellow'].forEach((k,i)=>Object.assign(poses[k],{x:(i-1)*.8,y:0,z:.45}));selected='yellow';}else return false;
 }else if(adapter==='english_hinged_umbrella_mesh'){
  if(!['closed','open','tilt'].includes(id))return false;opening=(id==='closed'?10:65)*Math.PI/180;
  if(id==='tilt')Object.assign(poses.umbrella,{x:.45,z:.2,angle:Math.PI/9,tilt:Math.PI/9});selected='umbrella';
 }
 modelState=id;createScene();drawModel();return true;
}
"""


def legacy_model_engine(adapter):
    source = shared.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    replacement = "const adapter=" + shared.js(adapter) + ";let selected='',modelState='initial',opening=10*Math.PI/180,wingAngle=0;const poses={};"
    if source.count(anchor) != 1:
        raise ValueError('mesh_pose_anchor_changed')
    source = source.replace(anchor, replacement)
    a, b = source.index('function createScene(){'), source.index('\nfunction compile(')
    source = source[:a] + MESH_BUILDERS + ADAPTER_STATES + source[b:]
    anchor = 'const world=multiply(translate(p.x,0,p.z),multiply(rotateY(p.angle),m.local));'
    replacement = 'const world=multiply(translate(p.x,p.y||0,p.z),multiply(rotateY(p.angle),multiply(rotateX(p.tilt||0),m.local)));'
    if source.count(anchor) != 1:
        raise ValueError('mesh_world_anchor_changed')
    source = source.replace(anchor, replacement)
    source = source.replace('createScene();document.getElementById', 'resetGeometry();createScene();document.getElementById')
    return source


MODEL_CONTROLS = r"""
const config=CONFIG;let visited=new Set();
function refreshControls(){document.getElementById('finish').disabled=interactionBusy||visited.size<config.states.length;}
function onCueCompleted(id){const state=config.states.find(s=>s.observationCueId===id);if(state)visited.add(state.sceneStateId);}
function displayed(signal){return new Promise((resolve,reject)=>{let done=false,frame1,frame2;const finish=error=>{if(done)return;done=true;clearTimeout(timer);cancelAnimationFrame(frame1);cancelAnimationFrame(frame2);signal.removeEventListener('abort',abort);error?reject(error):resolve(true);};const abort=()=>finish(new Error('cancelled'));const timer=setTimeout(()=>finish(new Error('render-timeout')),1500);signal.addEventListener('abort',abort,{once:true});if(signal.aborted||document.hidden){abort();return;}frame1=requestAnimationFrame(()=>{frame2=requestAnimationFrame(()=>finish());});});}
function clearStateSelection(){document.querySelectorAll('[data-state]').forEach(b=>b.classList.remove('selected'));}
function applyModel(id){if(interactionBusy)return;const state=config.states.find(s=>s.sceneStateId===id);if(!state)return;run(async signal=>{if(!gl){await narrate(config.retry,signal);return;}if(!commitState(id))return;document.querySelectorAll('[data-state]').forEach(b=>b.classList.toggle('selected',b.dataset.state===id));await displayed(signal);await narrate(state.observationCueId,signal);});}
function manipulate(delta,rotation){if(interactionBusy||!gl)return;const p=poses[selected];if(!p)return;if(p.x+delta< -2.35||p.x+delta>2.35){run(signal=>narrate(config.retry,signal));return;}p.x+=delta;p.angle+=rotation;createScene();drawModel();}
config.states.forEach(s=>listen('state-'+s.sceneStateId,()=>applyModel(s.sceneStateId)));
listen('start',()=>run(async signal=>{if(!gl){await narrate(config.retry,signal);return;}await displayed(signal);await narrate(config.intro,signal);}));listen('replay',replay);listen('left',()=>manipulate(-.25,0));listen('right',()=>manipulate(.25,0));listen('rotate',()=>manipulate(0,Math.PI/8));
function reset(){run(async signal=>{resetGeometry();visited.clear();clearStateSelection();await displayed(signal);await narrate(config.reset,signal);});}
listen('reset',reset);listen('finish',()=>{if(interactionBusy||visited.size<config.states.length)return;run(signal=>narrate(config.complete,signal));});listen('model-retry',()=>{cancelOperation();location.reload();});
function applyTeacherState(state){const keys=Object.keys(state);if(keys.length!==1||keys.some(k=>!['sceneStateId','objectTransform'].includes(k)))return;if(state.sceneStateId==='reset'){assisted=true;reset();return;}if(config.states.some(s=>s.sceneStateId===state.sceneStateId)){assisted=true;applyModel(state.sceneStateId);return;}const t=state.objectTransform;if(!t||typeof t!=='object'||Array.isArray(t)||!Object.keys(t).length||Object.keys(t).some(k=>!['moveX','rotateY'].includes(k))||!Object.values(t).every(Number.isFinite))return;if(Math.abs(t.moveX||0)>.25||Math.abs(t.rotateY||0)>Math.PI/8)return;assisted=true;manipulate(t.moveX||0,t.rotateY||0);}
initModel();refreshControls();
"""


SUPPORTED={
 'abacus_five_independent_beads':('one','three','five'),
 'array_tiles_rearrangement':('six','eight','rearrange'),
 'same_pivot_hinged_angle':('small','right','wide'),
 'cylinder_cone_mesh_comparison':('cylinder','cone','pair'),
 'round_tip_scissors_hinges':('open','close','turn'),
 'circuit_board_physical_switch':('open','closed','reopen'),
 'lever_beam_same_fulcrum':('level','leftdown','rightdown'),
 'bridge_beam_arch_truss':('beam','arch','truss'),
 'three_backpacks_handle_opening':('red','blue','yellow'),
 'bus_wheels_hinged_door':('straight','turn','door'),
 'cabinet_hinged_door_drawer_cup':('door','drawer','cup'),
 'bicycle_frame_pedal_steering':('park','pedal','steer'),
}


MESH = r'''
function rotateZ(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]);}
function lathe(profile){const out=[];for(let j=0;j<profile.length-1;j++)for(let i=0;i<32;i++){const p=(k,t)=>[profile[k][0]*Math.cos(t),profile[k][1],profile[k][0]*Math.sin(t)],a=i*Math.PI/16,b=(i+1)*Math.PI/16;triangle(out,p(j,a),p(j+1,a),p(j+1,b),[1,1,1],.7+.2*Math.cos(a));triangle(out,p(j,a),p(j+1,b),p(j,b),[1,1,1],.7+.2*Math.cos(a));}return out;}
function tube(a,b,r=.035){const d=b.map((v,i)=>v-a[i]),n=Math.hypot(...d);if(n<.0001)return[];const w=d.map(v=>v/n),t=Math.abs(w[1])<.9?[0,1,0]:[1,0,0],u=[w[1]*t[2]-w[2]*t[1],w[2]*t[0]-w[0]*t[2],w[0]*t[1]-w[1]*t[0]],ul=Math.hypot(...u);u.forEach((v,i)=>u[i]=v/ul);const v=[w[1]*u[2]-w[2]*u[1],w[2]*u[0]-w[0]*u[2],w[0]*u[1]-w[1]*u[0]],out=[];const p=(c,i)=>c.map((x,j)=>x+r*(u[j]*Math.cos(i*Math.PI/6)+v[j]*Math.sin(i*Math.PI/6)));for(let i=0;i<12;i++){triangle(out,p(a,i),p(b,i),p(b,i+1),[1,1,1],.82);triangle(out,p(a,i),p(b,i+1),p(a,i+1),[1,1,1],.82);}return out;}
function line(key,a,b,color,r=.035){geometries[key]=tube(a,b,r);part('focus',key,0,0,0,1,1,1,color);}
function ring(){const out=[],p=(a,b)=>[(.5+.065*Math.cos(b))*Math.cos(a),(.5+.065*Math.cos(b))*Math.sin(a),.065*Math.sin(b)];for(let i=0;i<32;i++)for(let j=0;j<8;j++){const a=i*Math.PI/16,b=(i+1)*Math.PI/16,c=j*Math.PI/4,d=(j+1)*Math.PI/4;triangle(out,p(a,c),p(b,c),p(b,d),[1,1,1],.84);triangle(out,p(a,c),p(b,d),p(a,d),[1,1,1],.84);}return out;}
geometries.ring=ring();geometries.cone=lathe([[0,0],[.5,0],[0,1]]);geometries.cup=lathe([[0,0],[.22,0],[.35,.5],[.31,.53],[.20,.07],[0,.07]]);
function transformed(shape,matrix,color){meshes.push({group:'focus',shape,color,local:matrix});}
const wood=[.66,.51,.32],blue=[.36,.58,.66],green=[.46,.65,.52],metal=[.64,.72,.68],red=[.73,.43,.38],yellow=[.78,.65,.32];
function buildAbacus(){
 for(const y of [.45,1.5])part('focus','box',0,y,0,3.2,.13,.17,wood);
 for(const x of [-1.55,1.55])part('focus','box',x,.98,0,.13,1.05,.17,wood);
 line('abacusRod',[-1.5,.98,0],[1.5,.98,0],metal,.035);
 const n={initial:0,one:1,three:3,five:5}[modelState];
 for(let i=0;i<5;i++){const x=i<n?-1.3+i*.28:1.3-(4-i)*.28;part('focus','sphere',x,.98,0,.23,.39,.31,red);}
}
function buildArray(){const count=modelState==='six'||modelState==='initial'?6:8,cols=modelState==='initial'?6:modelState==='rearrange'?2:count===6?3:4;for(let i=0;i<count;i++)part('focus','box',(i%cols-(cols-1)/2)*.53,.28,Math.floor(i/cols)*.48-.65,.4,.32,.36,green);}
function buildAngle(){const a=({initial:10,small:30,right:90,wide:120}[modelState])*Math.PI/180;line('fixedArm',[-1.2,.28,0],[1.2,.28,0],blue,.065);line('movingArm',[-1.2,.28,0],[-1.2+2.4*Math.cos(a),.28+2.4*Math.sin(a),0],wood,.065);part('focus','sphere',-1.2,.28,0,.19,.19,.19,yellow);}
function buildSolids(){const state=modelState;const cp=state==='cylinder'?[0,.8]:[-1.15,0],kp=state==='cone'?[0,.8]:[1.15,0];part('focus','cylinder',cp[0],.72,cp[1],1.05,1.44,1.05,blue);part('focus','cone',kp[0],0,kp[1],1.05,1.44,1.05,yellow);}
function buildScissors(){const a=['initial','close'].includes(modelState)?.09:.5,pivot=[0,1.0,0];for(const side of [-1,1]){const angle=side*a,turn=multiply(translate(...pivot),rotateZ(angle));transformed('box',multiply(turn,multiply(translate(0,.5,side*.025),scale(.10,1.03,.05))),metal);transformed('sphere',multiply(turn,multiply(translate(0,1.0,side*.025),scale(.10,.14,.05))),metal);transformed('ring',multiply(turn,multiply(translate(0,-.62,side*.025),scale(.55,.8,1))),blue);line('scissorHandle'+side,[0,1,side*.025],[-Math.sin(angle)*-.33,1+Math.cos(angle)*-.33,side*.025],metal,.05);}part('focus','sphere',0,1,.09,.16,.16,.09,wood);}
function buildCircuit(){
 part('focus','box',0,.12,0,3.6,.18,1.9,wood);part('focus','box',-1.22,.3,0,.38,.3,.8,green);part('focus','cylinder',-1.22,.48,0,.26,.7,.26,metal,0,Math.PI/2);
 const corners=[[-1.2,.26,-.65],[1.1,.26,-.65],[1.1,.26,.65],[-1.2,.26,.65],[-1.2,.26,.3]];for(let i=0;i<corners.length-1;i++)line('wire'+i,corners[i],corners[i+1],green,.035);
 part('focus','cylinder',1.1,.35,0,.4,.3,.4,metal);part('focus','sphere',1.1,.66,0,.46,.55,.46,[.82,.81,.63]);
 part('focus','box',0,.27,-.65,.55,.1,.3,blue);const end=modelState==='closed'?[.25,.33,-.65]:[.12,.76,-.65];line('switchBlade',[-.25,.33,-.65],end,metal,.06);part('focus','sphere',-.25,.33,-.65,.12,.12,.12,wood);part('focus','sphere',.25,.33,-.65,.12,.12,.12,wood);
}
function buildLever(){
 part('focus','cone',0,.1,0,1,.7,1,wood);const a={initial:0,level:0,leftdown:.32,rightdown:-.32}[modelState],pivot=multiply(translate(0,.86,0),rotateZ(a));transformed('box',multiply(pivot,scale(3.1,.15,.42)),blue);
 for(const x of [-1.18,1.18])transformed('box',multiply(pivot,multiply(translate(x,.27,0),scale(.35,.4,.38))),x<0?red:green);
}
function buildBridge(){
 part('focus','box',0,1.0,0,3.7,.16,.8,wood);for(const x of [-1.5,1.5])part('focus','box',x,.48,0,.32,.9,.9,metal);
 if(modelState==='arch')for(let i=0;i<20;i++){const p=t=>[1.47*Math.cos(t),.18+.72*Math.sin(t),0];line('arch'+i,p(i*Math.PI/20),p((i+1)*Math.PI/20),green,.09);}
 if(modelState==='truss')for(const z of [-.35,.35]){for(let i=0;i<4;i++){const x=-1.6+i*.8;line('braceA'+z+i,[x,1.1,z],[x+.4,1.85,z],blue,.045);line('braceB'+z+i,[x+.4,1.85,z],[x+.8,1.1,z],blue,.045);}line('top'+z,[-1.2,1.85,z],[1.2,1.85,z],blue,.05);}
}
function buildBackpacks(){
 const selectedIndex={initial:-1,red:0,blue:1,yellow:2}[modelState];
 [red,blue,yellow].forEach((color,i)=>{const x=modelState==='initial'?(i-1)*1.15:i===selectedIndex?0:(i-selectedIndex)*1.15,z=modelState==='initial'?-.1:i===selectedIndex?.6:-.5;
  part('focus','box',x,.14,z,.88,.08,.5,color);
  for(const dx of [-.42,.42])part('focus','box',x+dx,.72,z,.04,1.16,.5,color);
  for(const dz of [-.23,.23])part('focus','box',x,.72,z+dz,.8,1.16,.04,color);
  part('focus','box',x,.5,z+.31,.61,.45,.14,wood);transformed('ring',multiply(translate(x,1.55,z),scale(.42,.44,.7)),wood);
  for(const side of [-1,1])transformed('ring',multiply(translate(x+side*.24,.8,z-.25),scale(.26,.83,.75)),metal);
  const open=i===2&&modelState==='yellow',hinge=multiply(translate(x,1.3,z-.22),rotateX(open?-1.25:0));
  transformed('box',multiply(hinge,multiply(translate(0,0,.22),scale(.82,.06,.44))),color);
 });
}
function buildBus(){
 part('ground','box',0,-.015,0,4.8,.025,1.65,[.59,.65,.61]);for(const z of [-.69,.69])for(let i=0;i<8;i++)part('ground','box',-2.1+i*.6,.004,z,.32,.008,.035,[.88,.86,.68]);
 part('focus','box',0,.7,0,2.9,.85,.9,yellow);part('focus','box',.1,1.22,0,2.6,.22,.87,yellow);
 for(const x of [-.9,-.3,.3,.95])part('focus','box',x,.99,.47,.42,.35,.025,blue);
 for(const x of [-.92,.92])for(const z of [-.5,.5]){transformed('ring',multiply(translate(x,.3,z),scale(.56,.56,1)),metal);for(let i=0;i<4;i++){const a=i*Math.PI/2+(modelState==='straight'?Math.PI/4:0);line('busSpoke'+x+z+i,[x,.3,z],[x+.22*Math.cos(a),.3+.22*Math.sin(a),z],wood,.018);}}
 const hinge=multiply(translate(1.28,.65,.49),rotateY(modelState==='door'?-1.15:0));transformed('box',multiply(hinge,multiply(translate(-.22,0,0),scale(.43,.72,.055))),green);
}
function buildCabinet(){
 part('focus','box',0,.09,0,2,.16,.8,wood);part('focus','box',0,1.75,0,2,.14,.8,wood);part('focus','box',0,.82,0,2,.12,.8,wood);for(const x of [-.94,.94])part('focus','box',x,.94,0,.12,1.65,.8,wood);part('focus','box',0,.94,-.36,1.9,1.65,.08,wood);
 const hinge=multiply(translate(-.9,1.3,.42),rotateY(modelState==='initial'?0:-1.3));transformed('box',multiply(hinge,multiply(translate(.88,0,0),scale(1.76,.77,.08))),green);
 const z=modelState==='drawer'?.75:.05;part('focus','box',0,.46,z,1.65,.08,.63,wood);part('focus','box',0,.6,z+.32,1.65,.28,.08,green);for(const x of [-.8,.8])part('focus','box',x,.6,z,.06,.28,.63,wood);
 const cx=modelState==='cup'?.2:1.55,cz=modelState==='cup'?-.06:.15;part('focus','cup',cx,.9,cz,.72,.72,.72,blue);transformed('ring',multiply(translate(cx+.27,1.08,cz),scale(.24,.25,.8)),blue);
 part('ground','box',1.55,.82,.15,.73,.12,.72,wood);for(const dx of [-.27,.27])part('ground','box',1.55+dx,.4,.15,.07,.73,.6,wood);
}
function wheel(key,center,angle,steer=0){
 const transform=multiply(translate(...center),rotateY(steer));transformed('ring',multiply(transform,scale(1.1,1.1,1)),metal);
 for(let i=0;i<8;i++){const a=i*Math.PI/4+angle,p=[.49*Math.cos(a),.49*Math.sin(a),0],q=[p[0]*Math.cos(steer),p[1],-p[0]*Math.sin(steer)];line(key+'spoke'+i,center,center.map((x,j)=>x+q[j]),metal,.013);}
}
function buildBicycle(){
 const rear=[-1.1,.57,0],front=[1.05,.57,0],crank=[.05,.57,0],seat=[-.45,1.45,0],head=[.75,1.48,0],pedal=modelState==='pedal'?Math.PI/2:0,spin=modelState==='pedal'?.48:0,steer=modelState==='steer'?.45:0;
 const steerPoint=p=>{const x=p[0]-head[0],z=p[2]-head[2];return[head[0]+x*Math.cos(steer)+z*Math.sin(steer),p[1],head[2]-x*Math.sin(steer)+z*Math.cos(steer)];},frontNow=steerPoint(front);
 wheel('rear',rear,spin);wheel('front',frontNow,spin,steer);
 [[rear,seat],[seat,crank],[crank,rear],[seat,head],[head,crank]].forEach((pair,i)=>line('frame'+i,pair[0],pair[1],blue,.055));line('seatPost',seat,[-.5,1.68,0],metal);part('focus','box',-.5,1.7,0,.47,.08,.25,wood);
 for(const z of [-.09,.09])line('fork'+z,steerPoint([head[0],head[1],z]),steerPoint([front[0],front[1],z]),blue,.035);
 line('stem',head,steerPoint([.79,1.79,0]),metal);line('handle',steerPoint([.79,1.79,-.38]),steerPoint([.79,1.79,.38]),wood);
 part('focus','cylinder',crank[0],crank[1],0,.25,.12,.25,wood,0,Math.PI/2);
 for(const side of [-1,1]){const end=[crank[0]+side*.28*Math.cos(pedal),crank[1]+side*.28*Math.sin(pedal),side*.16];line('crank'+side,[...crank.slice(0,2),side*.1],end,wood,.035);part('focus','box',...end,.18,.06,.3,metal);}
}
function createScene(){meshes.length=0;part('ground','box',0,-.12,0,6.5,.18,3.6,[.77,.83,.70]);
 const builders={abacus_five_independent_beads:buildAbacus,array_tiles_rearrangement:buildArray,same_pivot_hinged_angle:buildAngle,cylinder_cone_mesh_comparison:buildSolids,round_tip_scissors_hinges:buildScissors,circuit_board_physical_switch:buildCircuit,lever_beam_same_fulcrum:buildLever,bridge_beam_arch_truss:buildBridge,three_backpacks_handle_opening:buildBackpacks,bus_wheels_hinged_door:buildBus,cabinet_hinged_door_drawer_cup:buildCabinet,bicycle_frame_pedal_steering:buildBicycle};
 if(!builders[adapter])throw new Error('unsupported-object');builders[adapter]();}
function resetGeometry(){poses.focus={x:0,y:0,z:0,angle:0};selected='focus';modelState='initial';if(gl){createScene();drawModel();}}
function commitState(id){if(!allowedStates.includes(id))return false;resetGeometry();modelState=id;
 if(adapter==='round_tip_scissors_hinges'&&id==='turn')poses.focus.angle=Math.PI/2;
 if(adapter==='bus_wheels_hinged_door'){poses.focus.x=id==='straight'?.45:0;poses.focus.angle=id==='turn'?Math.PI/4:0;}
 if(adapter==='three_backpacks_handle_opening'&&id==='blue')poses.focus.angle=Math.PI/5;
 if(adapter==='circuit_board_physical_switch'&&id==='reopen')poses.focus.angle=Math.PI/8;
 if(adapter==='bicycle_frame_pedal_steering'&&id==='park')poses.focus.z=.25;
 createScene();drawModel();return true;}
'''


def model_engine(adapter):
    if adapter not in SUPPORTED:raise ValueError('unsupported_exact_book_model')
    source=shared.WEBGL
    anchor="let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    replacement='const adapter='+shared.js(adapter)+';const allowedStates='+shared.js(SUPPORTED[adapter])+";let selected='focus',modelState='initial';const poses={focus:{x:0,y:0,z:0,angle:0}};"
    if source.count(anchor)!=1:raise ValueError('pinned_pose_anchor_changed')
    source=source.replace(anchor,replacement)
    a,b=source.index('function createScene(){'),source.index('\nfunction compile(')
    source=source[:a]+MESH+source[b:]
    source=source.replace('translate(p.x,0,p.z)','translate(p.x,p.y||0,p.z)')
    source=source.replace('createScene();document.getElementById','resetGeometry();createScene();document.getElementById')
    return source


STATE_PICTURES={
 'abacus_five_independent_beads':('abacus1','abacus3','abacus5'),
 'array_tiles_rearrangement':('array23','array24','array42'),
 'same_pivot_hinged_angle':('angle30','angle90','angle120'),
 'cylinder_cone_mesh_comparison':('cylinder','cone','solid_pair'),
 'round_tip_scissors_hinges':('scissors','scissors','scissors'),
 'circuit_board_physical_switch':('switch_open','switch_closed','circuit'),
 'lever_beam_same_fulcrum':('lever','lever_left','lever_right'),
 'bridge_beam_arch_truss':('bridge_beam','bridge_arch','bridge_truss'),
 'three_backpacks_handle_opening':('bagred','bagblue','bagopen'),
 'bus_wheels_hinged_door':('bus','bus','busdoor'),
 'cabinet_hinged_door_drawer_cup':('cabinet_open','cabinet_drawer','cup'),
 'bicycle_frame_pedal_steering':('bicycle','bicycle','bicycle'),
}


def pictures(adapter):
    keys=STATE_PICTURES[adapter];out=[]
    for i,key in enumerate(keys):
        shapes=shape(key)
        if adapter=='round_tip_scissors_hinges' and i==1:
            # Actual close view: two blades nearly together, handles remain apart.
            shapes='<path d="M72 20h7v60h-7Zm12 0h7v60h-7Z" fill="#b8c8c2" stroke="#738780" stroke-width="2"/><ellipse cx="63" cy="98" rx="17" ry="13" fill="none" stroke="#779c9e" stroke-width="8"/><ellipse cx="100" cy="98" rx="17" ry="13" fill="none" stroke="#779c9e" stroke-width="8"/><path d="m73 75-10 10m24-10 13 10" stroke="#738780" stroke-width="7"/><circle cx="81" cy="65" r="6" fill="#b38d5b"/>'
        if adapter=='round_tip_scissors_hinges' and i==2:shapes='<g transform="rotate(25 80 65)">'+shapes+'</g><path d="m20 31 20-10 4 18" fill="none" stroke="#a88b54" stroke-width="4"/>'
        if adapter=='bus_wheels_hinged_door' and i==1:shapes='<g transform="translate(26 9) rotate(-12 80 70) scale(.8)">'+shapes+'</g><path d="M17 107h61q41 0 41-70" fill="none" stroke="#8b9e83" stroke-width="5"/>'
        if adapter=='bicycle_frame_pedal_steering' and i==1:shapes+='<path d="M72 72q18-14 30 7m-10-6 10 6-8 10" fill="none" stroke="#b7925a" stroke-width="4"/>'
        if adapter=='bicycle_frame_pedal_steering' and i==2:shapes='<g transform="translate(0 7) rotate(-10 80 70)">'+shapes+'</g><path d="m109 30 22-8-3 18" fill="none" stroke="#b7925a" stroke-width="4"/>'
        if adapter=='three_backpacks_handle_opening' and i==2:shapes=bag('#c9aa5f',True)
        if adapter=='circuit_board_physical_switch' and i==2:shapes='<g transform="translate(13 8) rotate(-10 80 70) scale(.88)">'+shapes+'</g>'
        out.append(art(SUPPORTED[adapter][i]+'：观察模型的这一摆法',shapes))
    return out


TRAFFIC=r'''
function addAt(build,x,z,s,kind){const begin=meshes.length;build();for(let i=begin;i<meshes.length;i++){const m=meshes[i];m.group='focus';m.local=multiply(translate(x,0,z),multiply(scale(s,s,s),m.local));m.semanticKind=kind;}}
function walkPerson(){part('focus','sphere',0,1.16,0,.24,.27,.24,[.82,.67,.49]);part('focus','box',0,.82,0,.30,.43,.22,blue);for(const side of [-1,1]){line('leg'+side,[side*.07,.61,0],[side*.22,.12,side*.08],metal,.06);line('arm'+side,[side*.14,.95,0],[side*.26,.60,0],wood,.045);}part('focus','box',-.18,.83,-.06,.13,.3,.25,yellow);}
function littleBus(){part('focus','box',0,.65,0,2.4,.8,.85,yellow);for(const x of [-.75,-.2,.35,.9])part('focus','box',x,.84,.44,.38,.30,.025,blue);for(const x of [-.75,.75])for(const z of [-.47,.47])transformed('ring',multiply(translate(x,.27,z),scale(.5,.5,1)),metal);part('focus','sphere',-.15,.83,.44,.14,.15,.04,wood);}
function schoolBuilding(){part('focus','box',0,.75,0,1.1,1.5,.65,wood);part('focus','cone',0,1.49,0,1.5,.45,1.0,green);part('focus','box',0,.38,.34,.25,.75,.025,blue);for(const x of [-.32,.32])part('focus','box',x,1.05,.34,.23,.26,.03,[.78,.87,.83]);}
function parkTrees(){for(const x of [-.33,.33]){part('focus','cylinder',x,.48,0,.13,.96,.13,wood);part('focus','sphere',x,1.15,0,.65,.95,.65,green);}part('focus','box',0,.35,.4,.9,.08,.23,wood);for(const x of [-.32,.32])part('focus','box',x,.18,.4,.07,.35,.18,wood);}
function createScene(){meshes.length=0;part('ground','box',0,-.12,0,6.5,.18,4,[.78,.84,.72]);
 addAt(schoolBuilding,1.85,-1.1,.8,'school');if(theme==='travel')addAt(parkTrees,1.85,1.05,.9,'park');
 const positions={walk:[-1.9,-1.1],bike:[-1.9,0],bus:[-1.9,1.05]};
 let mode=null,dest=null;if(theme==='school'&&allowedStates.includes(modelState)){mode=modelState;dest='school';}
 if(theme==='travel'&&allowedStates.includes(modelState)){mode=modelState.endsWith('_bike')?'bike':'bus';dest=modelState.startsWith('park_')?'park':'school';}
 if(mode){positions[mode]=[.65,dest==='park'?1.05:-1.1];part('ground','box',-.5,.005,dest==='park'?1.05:-1.1,3.5,.015,.08,[.72,.61,.39]);}
 if(theme==='school')addAt(walkPerson,...positions.walk,.75,'walk');addAt(buildBicycle,...positions.bike,.48,'bike');addAt(littleBus,...positions.bus,.54,'bus');
 journey={mode,destination:dest,positions};}
function resetGeometry(){poses.focus={x:0,y:0,z:0,angle:0};selected='focus';modelState='initial';if(gl){createScene();drawModel();}}
function commitState(id){if(!allowedStates.includes(id))return false;resetGeometry();modelState=id;createScene();drawModel();return true;}
'''


def traffic_engine(theme,states):
    source=shared.WEBGL
    anchor="let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    replacement='const theme='+shared.js(theme)+';const allowedStates='+shared.js(states)+";let journey=null,selected='focus',modelState='initial';const poses={focus:{x:0,y:0,z:0,angle:0}};"
    assert source.count(anchor)==1;source=source.replace(anchor,replacement)
    utilities=MESH[:MESH.index('function buildAbacus')]
    bicycle=MESH[MESH.index('function wheel('):MESH.index('function createScene(){')]
    a,b=source.index('function createScene(){'),source.index('\nfunction compile(')
    source=source[:a]+utilities+bicycle+TRAFFIC+source[b:]
    return source.replace('createScene();document.getElementById','resetGeometry();createScene();document.getElementById')

