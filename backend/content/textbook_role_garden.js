/* Local articulated WebGL garden. No model-authored code is executed. */
function makeRoleGarden(canvas, labelRoot) {
  const gl = canvas.getContext('webgl', {antialias:true, alpha:false});
  if (!gl) throw new Error('webgl-unavailable');
  const id=()=>new Float32Array([1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]);
  function mul(a,b){const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;}
  function tr(x,y,z){const m=id();m[12]=x;m[13]=y;m[14]=z;return m;}
  function sc(x,y,z){const m=id();m[0]=x;m[5]=y;m[10]=z;return m;}
  function ry(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([c,0,-s,0,0,1,0,0,s,0,c,0,0,0,0,1]);}
  function rx(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([1,0,0,0,0,c,s,0,0,-s,c,0,0,0,0,1]);}
  function rz(a){const c=Math.cos(a),s=Math.sin(a);return new Float32Array([c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1]);}
  function project(p,m){const q=[0,0,0,0];for(let r=0;r<4;r++)for(let c=0;c<4;c++)q[r]+=m[c*4+r]*p[c];return q;}
  function shader(type,source){const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error('garden-shader');return s;}
  const program=gl.createProgram();
  gl.attachShader(program,shader(gl.VERTEX_SHADER,'attribute vec3 position;attribute vec3 normal;uniform mat4 matrix;uniform mat4 world;varying vec3 n;void main(){gl_Position=matrix*vec4(position,1.0);n=normalize(mat3(world)*normal);}'));
  gl.attachShader(program,shader(gl.FRAGMENT_SHADER,'precision mediump float;uniform vec3 color;varying vec3 n;void main(){float light=.62+.38*max(dot(normalize(n),normalize(vec3(-.5,.9,1.1))),0.);gl_FragColor=vec4(color*light,1.0);}'));
  gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error('garden-program');
  const loc={p:gl.getAttribLocation(program,'position'),n:gl.getAttribLocation(program,'normal'),m:gl.getUniformLocation(program,'matrix'),w:gl.getUniformLocation(program,'world'),c:gl.getUniformLocation(program,'color')};
  function surface(fn,rows,cols){const data=[];const push=(v)=>data.push(...v.slice(0,3),...v.slice(3));for(let j=0;j<rows;j++)for(let i=0;i<cols;i++){const a=fn(i/cols,j/rows),b=fn((i+1)/cols,j/rows),c=fn((i+1)/cols,(j+1)/rows),d=fn(i/cols,(j+1)/rows);[a,b,c,a,c,d].forEach(push);}const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);return {buffer,count:data.length/6};}
  const sphere=surface((u,v)=>{const a=u*Math.PI*2,b=v*Math.PI,n=[Math.sin(b)*Math.cos(a),Math.cos(b),Math.sin(b)*Math.sin(a)];return [...n.map(x=>x*.5),...n];},18,28);
  const cylinder=surface((u,v)=>{const a=u*Math.PI*2;return [Math.cos(a)*.5,v-.5,Math.sin(a)*.5,Math.cos(a),0,Math.sin(a)];},1,28);
  const dress=surface((u,v)=>{const a=u*Math.PI*2,r=.5-.2*v;return [Math.cos(a)*r,v-.5,Math.sin(a)*r,Math.cos(a),.2,Math.sin(a)];},1,28);
  const colors={skin:[1,.79,.61],hair:[.19,.15,.12],cream:[.97,.91,.76],coral:[.87,.40,.31],teal:[.25,.51,.52],yellow:[.92,.68,.22],blue:[.27,.38,.53],shoe:[.42,.27,.22]};
  const parts=[];
  function part(group,mesh,x,y,z,sx,sy,sz,color,az=0,tag=''){parts.push({group,mesh,color,tag,local:mul(tr(x,y,z),mul(rz(az),sc(sx,sy,sz)))});}
  function ball(...a){part(...a.slice(0,1),sphere,...a.slice(1));}
  const places={coral:[-1.85,0,0],teal:[0,0,.05],yellow:[1.85,0,0]};
  for(const key of Object.keys(places)){
    const girl=key==='coral',shirt=colors[key];
    for(const side of [-1,1]){
      ball(key,side*.19,.40,0,.22,.66,.24,key==='yellow'?colors.blue:colors.skin);
      if(key==='teal')ball(key,side*.19,.64,0,.29,.35,.30,colors.cream);
      ball(key,side*.19,.19,.02,.23,.22,.25,key==='yellow'?colors.blue:colors.cream);
      ball(key,side*.19,.075,.14,.34,.17,.48,girl?colors.coral:colors.blue);
      ball(key,side*.19,.065,.16,.35,.055,.50,colors.cream);
    }
    if(!girl)ball(key,0,.80,0,.68,.35,.44,key==='teal'?colors.cream:colors.blue);
    if(girl){part(key,dress,0,.78,0,.88,.65,.63,colors.cream);for(let j=0;j<12;j++){const a=j*2.399;ball(key,Math.sin(a)*.32,.61+(j%3)*.10,Math.cos(a)*.23,.045,.04,.02,j%2?colors.coral:colors.yellow);}}
    ball(key,0,1.18,0,.75,.74,.48,shirt);
    if(key==='yellow')ball(key,0,1.29,.228,.25,.45,.05,colors.cream);
    if(girl)ball(key,0,1.15,.235,.15,.56,.04,colors.cream);
    for(let j=0;j<3;j++)ball(key,.035,1.27-j*.12,.26,.045,.045,.026,colors.cream);
    ball(key,0,1.62,0,.22,.26,.24,colors.skin);
    ball(key,0,1.94,0,.79,.86,.67,colors.skin);
    ball(key,0,2.15,-.045,.85,.58,.71,colors.hair);
    if(girl){for(const side of [-1,1])ball(key,side*.31,1.99,-.03,.26,.71,.54,colors.hair);}
    for(let j=0;j<7;j++)ball(key,-.31+j*.097,2.16+Math.sin(j)*.045,.205,.20,.22,.23,colors.hair,-.25);
    for(const side of [-1,1]){
      ball(key,side*.40,1.94,0,.16,.23,.14,colors.skin);
      ball(key,side*.15,1.995,.316,.065,.093,.036,colors.hair);
      ball(key,side*.137,2.015,.337,.017,.02,.015,[1,1,1]);
      ball(key,side*.235,1.90,.295,.12,.047,.027,[.93,.55,.45]);
      ball(key,side*.16,2.075,.302,.105,.025,.025,colors.hair,side*.1);
    }
    ball(key,0,1.93,.352,.10,.095,.08,colors.skin);
    ball(key,0,1.843,.313,.14,.044,.025,[.49,.24,.20],0,'mouth');
    for(const side of [-1,1]){
      ball(key,side*.40,1.23,.01,.26,.47,.29,shirt,side*.18,'arm');
      ball(key,side*.46,.97,.055,.19,.33,.20,colors.skin,side*.18,'arm');
      ball(key,side*.49,.83,.095,.19,.22,.16,colors.skin,side*.1,'hand');
    }
  }
  ball('land',0,-.13,0,8,.24,4,[.67,.77,.52]);
  for(let j=0;j<10;j++)ball('land',-3.6+j*.8,-.005,.85+Math.sin(j*.8)*.23,.86,.055,.75,[.87,.78,.59]);
  for(const side of [-1,1]){
    part('land',cylinder,side*3,1.0,-1.0,.23,2,.23,[.48,.33,.22]);
    ball('land',side*3,2.15,-1,1.65,1.2,1.35,[.46,.66,.36]);ball('land',side*2.6,2.5,-1.1,1.2,1.0,1.1,[.58,.73,.43]);
    for(let j=0;j<7;j++){
      const x=side*(2.4+j*.13),z=.8+(j%3)*.22;
      part('land',cylinder,x,.12,z,.035,.27,.035,[.32,.50,.24]);
      for(let k=0;k<5;k++){const a=k*Math.PI*.4;ball('land',x+Math.cos(a)*.073,.26,z+Math.sin(a)*.073,.10,.045,.10,j%2?[.95,.89,.75]:[.87,.61,.53]);}
      ball('land',x,.272,z,.065,.045,.065,[.91,.69,.25]);
    }
  }
  let yaw=-.12,pitch=.10,roles={speakerCharacterId:'coral',listenerCharacterId:'teal',thirdCharacterId:'yellow'},showLabels=true,drag=null,view=id(),disposed=false,last=0;
  const labels={};for(const key of Object.keys(places)){const e=document.createElement('span');labelRoot.appendChild(e);labels[key]=e;}
  function resize(){const box=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.max(1,Math.round(box.width*dpr));canvas.height=Math.max(1,Math.round(box.height*dpr));gl.viewport(0,0,canvas.width,canvas.height);}
  function draw(now){
    if(disposed)return;requestAnimationFrame(draw);if(document.hidden||now-last<32)return;last=now;
    const width=Math.max(4.2,2.0*canvas.width/canvas.height),height=width*canvas.height/canvas.width;const projection=id();projection[0]=1/width;projection[5]=1/height;projection[10]=-.08;
    view=mul(projection,mul(rx(pitch),mul(ry(yaw),tr(0,-1.1,0))));
    gl.enable(gl.DEPTH_TEST);gl.clearColor(.91,.94,.88,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.useProgram(program);
    for(const p of parts){let world=p.local;const place=places[p.group];if(place){const listener=places[roles.listenerCharacterId],speaker=places[roles.speakerCharacterId];const target=p.group===roles.speakerCharacterId?listener:speaker;const facing=Math.atan2(target[0]-place[0],3.2);world=mul(tr(...place),mul(ry(facing),p.local));if(p.tag==='mouth'&&p.group===roles.speakerCharacterId)world=mul(world,sc(1,1.35+Math.sin(now*.012)*.3,1));}
      gl.bindBuffer(gl.ARRAY_BUFFER,p.mesh.buffer);gl.enableVertexAttribArray(loc.p);gl.enableVertexAttribArray(loc.n);gl.vertexAttribPointer(loc.p,3,gl.FLOAT,false,24,0);gl.vertexAttribPointer(loc.n,3,gl.FLOAT,false,24,12);gl.uniformMatrix4fv(loc.m,false,mul(view,world));gl.uniformMatrix4fv(loc.w,false,world);gl.uniform3fv(loc.c,p.color);gl.drawArrays(gl.TRIANGLES,0,p.mesh.count);
    }
    for(const [key,place] of Object.entries(places)){const q=project([place[0],2.64,place[2],1],view),e=labels[key];e.hidden=!showLabels;e.textContent=key===roles.speakerCharacterId?'我':key===roles.listenerCharacterId?'你':'他';e.style.left='clamp(26px,'+(q[0]*.5+.5)*100+'%,calc(100% - 26px))';e.style.top='max(50px,'+(.5-q[1]*.5)*100+'%)';}
  }
  canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,yaw,pitch};canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(drag){yaw=drag.yaw+(e.clientX-drag.x)*.007;pitch=Math.max(-.05,Math.min(.55,drag.pitch+(e.clientY-drag.y)*.003));}});
  canvas.addEventListener('pointerup',()=>{drag=null;});canvas.addEventListener('pointercancel',()=>{drag=null;});
  const observer=new ResizeObserver(resize);observer.observe(canvas);resize();requestAnimationFrame(draw);
  return {setRoles(value,reveal=true){roles=value;showLabels=reveal;},reveal(){showLabels=true;},rotate(){yaw+=.35;},reset(){yaw=-.12;pitch=.10;},dispose(){disposed=true;observer.disconnect();Object.values(labels).forEach(e=>e.remove());[sphere,cylinder,dress].forEach(m=>gl.deleteBuffer(m.buffer));gl.deleteProgram(program);}};
}
