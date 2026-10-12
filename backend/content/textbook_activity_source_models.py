"""Finite concrete models for the next source-aligned authoring families.

These original meshes are illustrations, not experimental evidence. Registration
in the activity IR remains explicit by subject/grade and exact three states; no
task ID or arbitrary script chooses a model. All state pictures must be supplied
by the frozen design, rather than generated as placeholder geometry here.
"""
from content import textbook_activity_templates as shared
from content import textbook_activity_models as common_models


SUPPORTED = {
    "five_counters_join_remove": ("two_plus_one", "three_plus_two", "five_remove_two"),
    "chinese_chick_duck_positions_scene": ("chicken_ahead", "duck_ahead", "side_by_side"),
    "chinese_spring_observation_scene": ("willow_near", "grass_near", "flowers_near"),
    "equal_groups_array_scene": ("array23", "array24", "array42"),
    "english_schoolthings_semantic_scene": ("pencil_near", "ruler_near", "eraser_near"),
    "english_food_requests_semantic_scene": ("noodles_near", "milk_near", "apple_near"),
    "water_container_observation_scene": ("cup", "dish", "bottle"),
    "plant_habitats_observation_scene": ("forest", "pond", "grassland"),
    "fruit_shape_observation_scene": ("apple_near", "pear_near", "orange_near"),
}
FAMILIES = {
    "five_counters_join_remove": ("math", 1),
    "chinese_chick_duck_positions_scene": ("chinese", 1),
    "chinese_spring_observation_scene": ("chinese", 2),
    "equal_groups_array_scene": ("math", 2),
    "english_schoolthings_semantic_scene": ("english", 3),
    "english_food_requests_semantic_scene": ("english", 3),
    "water_container_observation_scene": ("science", 1),
    "plant_habitats_observation_scene": ("science", 2),
    "fruit_shape_observation_scene": ("science", 1),
}


BUILDERS = r'''
let teachingState=null;
function semanticPart(kind,shape,x,y,z,sx,sy,sz,color,ry=0,rx=0){part('focus',shape,x,y,z,sx,sy,sz,color,ry,rx);meshes[meshes.length-1].semanticKind=kind;}
function semanticLine(kind,a,b,color,r=.035){const before=meshes.length;line(kind+before,a,b,color,r);meshes[meshes.length-1].semanticKind=kind;}
function addGroup(kind,build,x,y,z,s=1,yaw=0){const from=meshes.length;build();const transform=multiply(translate(x,y,z),multiply(rotateY(yaw),scale(s,s,s)));for(let i=from;i<meshes.length;i++){meshes[i].local=multiply(transform,meshes[i].local);meshes[i].semanticPiece=meshes[i].semanticPiece||meshes[i].semanticKind;meshes[i].semanticKind=kind;}}
function tray(x,z,width,color){semanticPart('tray','box',x,.15,z,width,.10,1.05,color);for(const side of [-1,1])semanticPart('tray','box',x+side*width/2,.22,z,.06,.18,1.05,color);}
function counters(){
 tray(-2.0,0,1.1,wood);tray(0,0,2.2,[.68,.76,.68]);tray(2.0,0,1.1,[.72,.63,.51]);
 const active={initial:0,two_plus_one:3,three_plus_two:5,five_remove_two:3}[modelState],items=[];
 for(let i=0;i<5;i++){
  const onMat=i<active,removed=!onMat&&modelState==='five_remove_two',area=onMat?'work':removed?'removed':'source',trayIndex=i-active,x=onMat?-.75+i*.38:(removed?2:-2)+(trayIndex%2-.5)*.36,z=onMat?0:removed?0:(Math.floor(trayIndex/2)-1)*.30;
  semanticPart('counter-'+i,'sphere',x,.43,z,.28,.28,.28,i<2?red:blue);items.push({id:i,onMat,area,x,z});
 }
 teachingState={family:adapter,activeCount:active,sourceCount:modelState==='five_remove_two'?0:5-active,removedCount:modelState==='five_remove_two'?2:0,totalCount:5,items,
  operation:modelState==='two_plus_one'?{before:2,join:1,after:3}:modelState==='three_plus_two'?{before:3,join:2,after:5}:modelState==='five_remove_two'?{before:5,remove:2,after:3}:null};
}
function duck(){
 semanticPart('duck-body','sphere',0,.55,0,.95,.54,.65,[.88,.88,.74]);semanticPart('duck-neck','cylinder',.35,.82,0,.24,.54,.24,[.88,.88,.74]);semanticPart('duck-head','sphere',.4,1.12,0,.38,.38,.34,[.88,.88,.74]);
 semanticPart('duck-flat-bill','sphere',.66,1.08,0,.38,.10,.21,yellow);semanticPart('duck-tail','sphere',-.5,.64,0,.34,.18,.26,[.88,.88,.74],0,-.55);
 for(const side of [-1,1]){semanticPart('duck-wing','sphere',-.03,.57,side*.28,.55,.11,.35,[.73,.76,.66]);semanticPart('duck-eye','sphere',.48,1.17,side*.14,.055,.055,.035,[.12,.19,.17]);
  semanticLine('duck-leg',[side*.12,.30,.04],[side*.12,.10,.04],yellow,.028);semanticPart('duck-foot','sphere',side*.12,.08,.13,.25,.055,.25,yellow);}
}
function chick(){
 semanticPart('chick-body','sphere',0,.54,0,.64,.70,.57,yellow);semanticPart('chick-head','sphere',.18,.99,0,.48,.48,.44,yellow);transformed('cone',multiply(translate(.42,.95,0),multiply(rotateZ(-Math.PI/2),scale(.17,.17,.17))),[.79,.45,.25]);meshes[meshes.length-1].semanticKind='chick-beak';
 for(const x of [.04,.15,.26])semanticPart('chick-comb','sphere',x,1.25,0,.13,.20,.10,red);
 for(const side of [-1,1]){semanticPart('chick-wing','sphere',-.06,.60,side*.26,.31,.13,.32,[.85,.73,.39]);semanticPart('chick-eye','sphere',.28,1.06,side*.18,.055,.055,.035,[.12,.19,.17]);
  semanticLine('chick-leg',[side*.14,.25,0],[side*.14,.075,0],[.74,.47,.25],.024);for(const toe of [-1,0,1])semanticLine('chick-toe',[side*.14,.075,0],[side*.14+toe*.075,.04,.19],[.74,.47,.25],.018);}
 semanticPart('chick-tail','sphere',-.33,.64,0,.27,.15,.28,[.83,.70,.36],0,-.4);
}
function birds(){
 semanticPart('path','box',0,.02,0,5.5,.045,3.4,[.76,.68,.50]);
 const positions={initial:{chick:[-1.5,.05,-.4],duck:[-.5,.05,.4]},chicken_ahead:{chick:[.85,.05,0],duck:[-.85,.05,0]},duck_ahead:{chick:[-.85,.05,0],duck:[.85,.05,0]},side_by_side:{chick:[0,.05,-1.2],duck:[0,.05,1.2]}}[modelState];
 addGroup('duck',duck,...positions.duck,.9);addGroup('chick',chick,...positions.chick,.85);
 teachingState={family:adapter,heading:'right',groundOnly:true,chicken:{x:positions.chick[0],z:positions.chick[2]},duck:{x:positions.duck[0],z:positions.duck[2]},ahead:modelState==='chicken_ahead'?'chicken':modelState==='duck_ahead'?'duck':null};
}
function willow(){semanticLine('trunk',[0,.05,0],[0,1.85,0],wood,.075);for(const side of [-1,1])for(let i=0;i<3;i++){const end=[side*(.3+i*.13),1.55-i*.15,(i-1)*.12];semanticLine('willow-branch',[0,1.65,0],end,wood,.023);semanticLine('willow-droop',end,[end[0]+side*.12,end[1]-.55,end[2]],green,.012);for(let j=0;j<4;j++)semanticPart('willow-leaf','sphere',end[0]+side*.11,end[1]-.1-j*.12,end[2],.08,.25,.045,green,0,side*.3);}}
function grass(){for(let i=0;i<7;i++){const x=(i-3)*.1,h=.5+(i%3)*.17;semanticLine('grass-blade',[0,.05,0],[x,h,(i%2)*.1],green,.032);semanticPart('grass-leaf','sphere',x*.6,h*.6,0,.09,h*.8,.055,green,0,-x*.55);}}
function flowers(){for(const [x,color]of [[-.5,red],[0,yellow],[.5,[.56,.44,.71]]]){semanticLine('flower-stem',[x,.04,0],[x,.77,0],green,.026);semanticPart('flower-leaf','sphere',x+.12,.35,0,.35,.07,.17,green,0,-.4);for(let i=0;i<5;i++){const a=i*Math.PI*2/5;semanticPart('flower-petal','sphere',x+.18*Math.cos(a),.89+.18*Math.sin(a),.03,.23,.26,.07,color,0,a);}semanticPart('flower-center','sphere',x,.89,.085,.15,.15,.06,[.71,.49,.22]);}}
function spring(){const positions={willow:[-1.7,.07,-.35],grass:[0,.07,-.35],flowers:[1.65,.07,-.35]};const chosen=modelState.endsWith('_near')?modelState.slice(0,-5):null;if(chosen)positions[chosen]=[0,.07,.85];for(const [key,build]of Object.entries({willow,grass,flowers}))addGroup(key,build,...positions[key],key==='willow'?.8:1);teachingState={family:adapter,selected:chosen,positions,notGrowthSimulation:true};}
function groups(){const layout={initial:[0,0],array23:[2,3],array24:[2,4],array42:[4,2]}[modelState],rows=layout[0],cols=layout[1],active=rows*cols,items=[];tray(-2.15,0,.8,wood);for(let i=0;i<8;i++){const onBoard=i<active,x=onBoard?(i%cols-(cols-1)/2)*.52+.3:-2.35+(i%2)*.3,z=onBoard?(Math.floor(i/cols)-(rows-1)/2)*.46:Math.floor((i-active)/2)*.30-.45;semanticPart('array-tile-'+i,'box',x,.27,z,.38,.30,.34,green);items.push({id:i,onBoard,row:onBoard?Math.floor(i/cols):null,col:onBoard?i%cols:null,x,z});}teachingState={family:adapter,rows,cols,activeCount:active,sourceCount:8-active,totalCount:8,items};
}
function pencil(){
 semanticPart('pencil-body','cylinder',0,.91,0,.20,1.25,.20,yellow);semanticPart('pencil-wood','cone',0,.30,0,.20,.20,.20,wood,0,Math.PI);semanticPart('pencil-tip','cone',0,.13,0,.075,.08,.075,[.18,.23,.22],0,Math.PI);semanticPart('pencil-eraser','cylinder',0,1.60,0,.20,.17,.20,red);semanticPart('pencil-band','cylinder',0,1.48,0,.21,.08,.21,metal);
}
function ruler(){
 semanticPart('ruler','box',0,.85,0,.32,1.5,.075,[.82,.72,.48]);for(let i=0;i<=10;i++)semanticPart('ruler-tick','box',-.12,.18+i*.133,.044,i%5===0?.17:.08,.018,.012,[.37,.40,.31]);
}
function eraser(){semanticPart('eraser','box',0,.31,0,.66,.45,.38,[.88,.78,.63]);semanticPart('eraser-sleeve','box',.10,.31,0,.46,.46,.39,blue);}
function schoolthings(){
 tray(0,0,3.8,wood);const posesByKey={pencil:[-1.2,.12,-.25],ruler:[0,.12,-.25],eraser:[1.25,.12,-.25]};
 const chosen=modelState==='initial'?null:modelState.slice(0,-5);if(chosen)posesByKey[chosen]=[0,.12,.85];
 for(const [name,build] of Object.entries({pencil,ruler,eraser})){const p=posesByKey[name];addGroup(name,build,...p,1,chosen===name?.18:0);}
 teachingState={family:adapter,selected:chosen,positions:posesByKey,requestThenReceive:true};
}
function noodles(){
 semanticPart('noodle-bowl','cup',0,.1,0,1.5,.7,1.5,blue);for(let i=0;i<5;i++)for(let k=0;k<8;k++){const x=-.25+k*.07,z=-.20+i*.09,y=.43+.02*Math.sin(k*1.4+i);semanticLine('noodle',[x,y,z],[x+.07,.43+.02*Math.sin((k+1)*1.4+i),z],yellow,.018);}semanticLine('chopstick1',[-.4,.5,-.3],[.5,.54,.1],wood,.025);semanticLine('chopstick2',[-.42,.5,-.25],[.47,.54,.15],wood,.025);
}
function milk(){for(const y of [.15,.88])semanticPart('glass-rim','ring',0,y,0,.65,.65,.65,[.72,.84,.81],0,Math.PI/2);for(const side of [-1,1])semanticLine('glass-outline',[side*.30,.15,0],[side*.30,.88,0],[.72,.84,.81],.015);semanticPart('white-milk','cylinder',0,.43,0,.54,.52,.54,[.96,.94,.84]);}
function apple(){semanticPart('apple-body','sphere',0,.42,0,.66,.65,.58,red);for(const side of [-1,1])semanticPart('apple-lobe','sphere',side*.14,.62,0,.32,.30,.39,red);semanticLine('apple-stem',[0,.73,0],[.04,.91,0],wood,.026);semanticPart('apple-leaf','sphere',.16,.86,0,.26,.055,.13,green,0,-.35);}
function pear(){semanticPart('pear-base','sphere',0,.39,0,.71,.66,.64,[.72,.76,.36]);semanticPart('pear-neck','sphere',0,.73,0,.37,.55,.36,[.72,.76,.36]);semanticLine('pear-stem',[0,.97,0],[.08,1.15,0],wood,.027);semanticPart('pear-leaf','sphere',.17,1.05,0,.29,.055,.14,green,0,-.4);}
function orange(){semanticPart('orange-body','sphere',0,.44,0,.76,.69,.73,[.94,.56,.16]);semanticPart('orange-calyx','sphere',0,.79,0,.17,.035,.17,green);for(let i=0;i<14;i++){const a=i*Math.PI*2/14;semanticPart('orange-peel-mark','sphere',.34*Math.sin(a),.45+.10*Math.cos(a*3),.34*Math.cos(a),.025,.025,.025,[.76,.40,.11]);}}
function fruits(){tray(0,0,4.1,wood);const positions={apple:[-1.3,.13,-.3],pear:[0,.13,-.3],orange:[1.3,.13,-.3]},chosen=modelState==='initial'?null:modelState.slice(0,-5);if(chosen)positions[chosen]=[0,.13,.92];for(const [key,build]of Object.entries({apple,pear,orange}))addGroup(key,build,...positions[key],1,chosen===key?.22:0);teachingState={family:adapter,selected:chosen,positions,visualObservationOnly:true,notTasteOrExperimentEvidence:true};}
function food(){
 tray(0,0,3.9,wood);const items={noodles:[-1.2,.1,-.2],milk:[0,.1,-.2],apple:[1.2,.1,-.2]},chosen=modelState==='initial'?null:modelState.slice(0,-5);if(chosen)items[chosen]=[0,.1,.9];for(const [name,build]of Object.entries({noodles,milk,apple}))addGroup(name,build,...items[name]);teachingState={family:adapter,selected:chosen,positions:items,requestThenReceive:true};
}
function vessels(){
 const keys=['cup','dish','bottle'],x=[-1.5,0,1.5],active=keys.includes(modelState)?keys.indexOf(modelState):-1;
 const profiles={cup:[[.48,.15],[.49,1.25]],dish:[[.72,.15],[.82,.34]],bottle:[[.30,.15],[.32,1.15],[.15,1.38],[.15,1.6]]},glass=[.53,.69,.65];
 keys.forEach((key,i)=>{const profile=profiles[key];for(const [r,y]of profile)semanticPart(key,'ring',x[i],y,0,r*2,r*2,r*2,glass,0,Math.PI/2);
  for(let side=0;side<8;side++){const a=side*Math.PI/4;for(let j=0;j<profile.length-1;j++){const [r1,y1]=profile[j],[r2,y2]=profile[j+1];semanticLine(key,[x[i]+r1*Math.cos(a),y1,r1*Math.sin(a)],[x[i]+r2*Math.cos(a),y2,r2*Math.sin(a)],glass,.012);}}
  if(key==='cup')semanticPart(key,'ring',x[i]+.53,.77,0,.50,.65,.13,glass);
  if(i===active){const volume=.245*.245*.92,shape={cup:{r:.43,h:volume/(.43*.43)},dish:{r:.68,h:volume/(.68*.68)},bottle:{r:.245,h:.92}}[key];semanticPart('model-water','cylinder',x[i],.2+shape.h/2,0,shape.r*2,shape.h,shape.r*2,blue);}
 });
 teachingState={family:adapter,waterContainer:active<0?null:keys[active],vesselProfiles:profiles,transparentOutline:true,illustrativeShapeOnly:true,notMeasurementEvidence:true,notExperimentEvidence:true};
}
function forest(){semanticPart('forest-soil','box',0,.1,0,1.15,.15,1.0,wood);for(const x of [-.3,.3]){semanticLine('forest-trunk',[x,.15,0],[x,.88,0],wood,.055);semanticPart('forest-crown','sphere',x,1.05,0,.66,.80,.66,green);}}
function pond(){semanticPart('pond-water','cylinder',0,.12,0,1.25,.05,1.1,blue);for(const side of [-1,1])for(let i=0;i<3;i++){const x=side*(.3+i*.05),z=(i-1)*.17;semanticLine('reed',[x,.15,z],[x,.95+i*.08,z],green,.022);semanticPart('reed-leaf','sphere',x+side*.1,.65,z,.055,.60,.08,green,0,side*.25);semanticPart('reed-head','cylinder',x,1.0+i*.08,z,.08,.25,.08,wood);}}
function grassland(){semanticPart('grassland-soil','box',0,.10,0,1.4,.15,1.1,wood);for(const x of [-.4,0,.4])for(const z of [-.3,.2])addGroup('grass-clump',grass,x,.15,z,.45);semanticPart('grassland-rock','sphere',.43,.27,.39,.35,.24,.27,[.52,.55,.50],.25,.15);semanticPart('grassland-rock','sphere',.14,.23,.43,.21,.16,.18,[.61,.62,.56],-.2,.13);}
function habitats(){const positions={forest:[-1.7,.04,-.35],pond:[0,.04,-.35],grassland:[1.7,.04,-.35]},chosen=modelState==='initial'?null:modelState;if(chosen)positions[chosen]=[0,.04,.95];for(const [key,build]of Object.entries({forest,pond,grassland}))addGroup(key,build,...positions[key]);if(chosen){const p=positions[chosen];semanticPart('observation-marker','ring',p[0],.08,p[2],1.5,1.5,1.5,yellow,0,Math.PI/2);}teachingState={family:adapter,selected:chosen,positions,notPlantNeedsInstruction:true};
}
function createScene(){meshes.length=0;part('ground','box',0,-.15,0,6.5,.16,3.6,[.77,.83,.70]);const builders={five_counters_join_remove:counters,chinese_chick_duck_positions_scene:birds,chinese_spring_observation_scene:spring,equal_groups_array_scene:groups,english_schoolthings_semantic_scene:schoolthings,english_food_requests_semantic_scene:food,water_container_observation_scene:vessels,plant_habitats_observation_scene:habitats,fruit_shape_observation_scene:fruits};builders[adapter]();}
function resetGeometry(){poses.focus={x:0,y:0,z:0,angle:0};selected='focus';modelState='initial';if(gl){createScene();drawModel();}}
function commitState(id){if(!allowedStates.includes(id))return false;resetGeometry();modelState=id;
 createScene();drawModel();return true;}
'''


def engine(adapter):
    if adapter not in SUPPORTED:
        raise ValueError("unsupported_source_semantic_family")
    source = shared.WEBGL
    anchor = "let selected='tree',modelState='initial';const poses={tree:{x:-2,z:0,angle:0},bird:{x:0,z:0,angle:0},field:{x:2,z:0,angle:0}};"
    if source.count(anchor) != 1:
        raise ValueError("source_mesh_pose_anchor_changed")
    source = source.replace(anchor, "const adapter="+shared.js(adapter)+";const allowedStates="+shared.js(SUPPORTED[adapter])+";let selected='focus',modelState='initial';const poses={focus:{x:0,y:0,z:0,angle:0}};")
    utilities = common_models.MESH[:common_models.MESH.index("function buildAbacus")]
    start, end = source.index("function createScene(){"), source.index("\nfunction compile(")
    source = source[:start]+utilities+BUILDERS+source[end:]
    source = source.replace("translate(p.x,0,p.z)", "translate(p.x,p.y||0,p.z)")
    source = source.replace("createScene();document.getElementById", "resetGeometry();createScene();document.getElementById")
    if adapter == "chinese_chick_duck_positions_scene":
        source = source.replace("multiply(rotateY(-.35),translate(0,-.9,0))", "multiply(rotateY(0),translate(0,-.9,0))")
        source = source.replace("multiply(rotateX(.35),", "multiply(rotateX(.6),")
    return source
