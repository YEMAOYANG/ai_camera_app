// Sokoban with category docks. A push can park a token only in a matching
// dock. Plan where to stand and the order of the deliveries. Sample data owns
// the pictured items and which property groups them, never this mechanic.
K.gameTemplates.sortingDepot = config => {
  const {box,center,create,bot,sprite,token,validToken}=Classic;
  const keys=['left','right','up','down'];
  const step=[[-1,0],[1,0],[0,-1],[0,1]];
  const models=new Map();
  const cell=(m,x,y)=>y*m.cols+x;
  const encode=s=>s.p+':'+s.items.join(',');
  const destination=pos=>pos<0?-1-pos:pos;
  const between=(n,a,b)=>Number.isInteger(n)&&n>=a&&n<=b;

  function move(m,s,k){
    const offset=p=>{
      const x=p%m.cols+step[k][0],y=Math.floor(p/m.cols)+step[k][1];
      return x<0||y<0||x>=m.cols||y>=m.rows?-1:cell(m,x,y);
    };
    const at=offset(s.p);
    if(at<0||m.floor[at]==='#'||m.docks.has(at))return null;
    const item=s.items.indexOf(at);
    if(item<0)return {state:{p:at,items:s.items}};
    const end=offset(at),dock=m.docks.get(end);
    if(end<0||m.floor[end]==='#'||s.items.includes(end)||s.items.includes(-1-end))return null;
    if(dock&&dock.group!==m.items[item].group)return {wrong:true,at:end,group:m.items[item].group};
    const items=s.items.slice();
    items[item]=dock?-1-end:end;
    return {state:{p:at,items},dock,item};
  }

  function solve(m,start){
    const queue=new Map(),seen=new Set([encode(start)]);
    let lowest=Infinity;
    const dist=(a,b)=>Math.abs(a%m.cols-b%m.cols)+Math.abs(Math.floor(a/m.cols)-Math.floor(b/m.cols));
    function enqueue(node){
      // Try routes toward reachable category docks first; the pilot need not
      // find the shortest route. Only the shared move rule can accept it.
      const {s,steps}=node;
      const estimate=s.items.reduce((sum,pos,i)=>pos<0?sum:sum+Math.min(...m.targets[i]
        .filter(to=>!s.items.includes(-1-to)).map(to=>dist(pos,to))),0);
      if(!Number.isFinite(estimate))return;
      const priority=steps+4*estimate;
      if(!queue.has(priority))queue.set(priority,[]);
      queue.get(priority).push(node);
      lowest=Math.min(lowest,priority);
    }
    enqueue({s:start,parent:null,key:-1,steps:0});
    for(let i=0;queue.size&&i<38000;i++){
      if(!queue.has(lowest))lowest=Math.min(...queue.keys());
      const bucket=queue.get(lowest),node=bucket.pop(),{s}=node;
      if(!bucket.length)queue.delete(lowest);
      if(s.items.every(p=>p<0)){
        const route=[];
        for(let j=node;j.parent;j=j.parent)route.unshift(j.key);
        return route;
      }
      for(let k=0;k<keys.length;k++){
        const next=move(m,s,k)?.state;
        if(!next)continue;
        const id=encode(next);
        if(!seen.has(id)){seen.add(id);enqueue({s:next,parent:node,key:k,steps:node.steps+1});}
      }
    }
    return null;
  }

  function validate(l,level){
    if(!Array.isArray(l.map)||!between(l.map.length,4,7)||typeof l.map[0]!=='string'||
      !between(l.map[0].length,6,12)||!l.map.every(row=>typeof row==='string'&&row.length===l.map[0].length&&/^[#.S]+$/.test(row))||
      !(l.step>=.13&&l.step<=.44)||!Array.isArray(l.items)||!between(l.items.length,2,5)||
      !Array.isArray(l.docks)||l.docks.length!==l.items.length)throw new Error('invalid depot level');
    const floor=l.map.join(''),cols=l.map[0].length,rows=l.map.length,docks=new Map(),occupied=new Set([floor.indexOf('S')]);
    if(floor.split('S').length!==2)throw new Error('depot needs exactly one start');
    const at=(point,mark)=>{
      const {x,y,group}=point||{},p=y*cols+x;
      if(!between(x,0,cols-1)||!between(y,0,rows-1)||floor[p]!=='.'||occupied.has(p)||!validToken(mark)||!validToken(group))
        throw new Error('invalid depot item or dock');
      occupied.add(p);
      return p;
    };
    const items=l.items.map(p=>at(p,p?.token));
    for(const d of l.docks)docks.set(at(d,d?.sample),d);
    const targets=l.items.map(item=>[...docks].filter(([,d])=>d.group===item.group).map(([p])=>p));
    const m={floor,cols,rows,docks,targets,items:l.items,initial:{p:floor.indexOf('S'),items}};
    m.solution=solve(m,m.initial);
    if(!m.solution?.length)throw new Error('depot level '+(level+1)+' has no route within search budget');
    models.set(l,m);
  }

  function reset(l){
    const m=models.get(l), s=Math.min(104,Math.floor(470/m.rows),Math.floor(910/m.cols));
    const {initial}=m;
    return {state:initial,history:[],route:m.solution,routeAt:0,solving:encode(initial),cool:0,help:false,
      ox:640-m.cols*s/2,oy:104+(476-m.rows*s)/2,s,slideStart:-Infinity,old:initial,pulse:0,wrongGroup:null};
  }
  const xy=(w,m,p)=>[w.ox+(p%m.cols+.5)*w.s,w.oy+(Math.floor(p/m.cols)+.5)*w.s];

  function update(w,l,input,dt,fb){
    const m=models.get(l);
    w.cool=Math.max(0,w.cool-dt);w.pulse=Math.max(0,w.pulse-dt);
    if(input.press('action')){
      const previous=w.history.pop();
      w.old=w.state;w.state=previous||m.initial;w.slideStart=null;w.cool=.22;w.pulse=.2;
      if(!previous)fb.resetCheckpoint();
      fb.move();fb.fx(...xy(w,m,w.state.p));return;
    }
    if(w.cool>0)return;
    const k=keys.findIndex(key=>input.held(key)||input.press(key));
    if(k<0)return;
    const result=move(m,w.state,k);
    w.cool=l.step*(w.help?1.18:1);
    if(result?.wrong){w.wrongGroup=result.group;fb.lost(...xy(w,m,result.at));return;}
    if(!result){w.pulse=.15;fb.move();return;}
    w.history.push(w.state);
    if(w.history.length>180)w.history.shift();
    w.old=w.state;w.state=result.state;w.slideStart=null;w.pulse=.18;
    fb.move();
    if(result.dock){
      w.wrongGroup=null;
      w.history.length=0; // Parked pieces stay parked until restarting the room.
      fb.award(...xy(w,m,destination(w.state.items[result.item])));
    }else if(result.item!==undefined)fb.fx(...xy(w,m,w.state.items[result.item]));
  }

  function draw(w,l,c,imgs,g){
    const m=models.get(l),s=w.s, scale=s/68;
    // Finish the slide even while the engine is holding a winning action
    // for narration or a teacher highlight, when physics stops updating.
    if(w.slideStart===null)w.slideStart=g.t;
    const slide=1-Math.max(0,1-(g.t-w.slideStart)/.15)**3;
    const middle=(p,q)=>{
      const [x,y]=xy(w,m,destination(p)),[tx,ty]=xy(w,m,destination(q));
      return [x+(tx-x)*slide,y+(ty-y)*slide];
    };
    box(c,w.ox-12,w.oy-12,m.cols*s+24,m.rows*s+24,23,'#223f34');
    for(let p=0;p<m.floor.length;p++){
      const [x,y]=xy(w,m,p),wall=m.floor[p]==='#';
      box(c,x-s/2+2,y-s/2+2,s-4,s-4,9,wall?'#557360':(p%2?'#f4dbac':'#ebc991'));
      if(wall)box(c,x-s/2+7,y-s/2+7,s-14,5,2,'#75917c');
    }
    const next=w.state.items.findIndex(p=>p>=0), group=w.wrongGroup??m.items[next]?.group;
    for(const [p,dock] of m.docks){
      const [x,y]=xy(w,m,p),parked=w.state.items.includes(-1-p);
      const radius=29*scale;
      box(c,x-radius,y-radius,radius*2,radius*2,12,parked?'#8cbd9c':w.help&&dock.group===group?'#ffdd77':'#b7c5a2');
      c.save();c.strokeStyle='#48725c';c.lineWidth=3;c.setLineDash([5,4]);K.draw.rr(c,x-radius+2,y-radius+2,radius*2-4,radius*2-4,11);c.stroke();c.restore();
      if(!parked)token(c,imgs,dock.sample,x,y,46*scale,46*scale,l.labels);
    }
    for(const [i,p] of w.state.items.entries()){
      const [x,y]=middle(w.old.items[i],p);
      if(p>=0)box(c,x-27*scale,y-26*scale,54*scale,52*scale,12,'#fff1d1');
      token(c,imgs,m.items[i].token,x,y,53*scale,53*scale,l.labels);
    }
    const [x,y]=middle(w.old.p,w.state.p);
    if(!sprite(c,imgs.frames[w.pulse>0?1:0]||imgs.frames[0],x,y,59*scale,57*scale)){
      box(c,x-23*scale,y-23*scale,46*scale,46*scale,17,'#b85337');
    }
  }

  return create(config,{
    backdrop:'#355247',controls:[...keys,['action','↶','撤回一步；没有可撤回的步骤时重来']],
    validate,reset,update,draw,goal:l=>l.items.length,adapt(w,n){w.help=n>=2;},
    player(w,l){return center(...xy(w,models.get(l),w.state.p),w.s*.9,w.s*.9);},
    target(w,l){
      const pos=w.state.items.find(p=>p>=0);
      return pos===undefined?null:center(...xy(w,models.get(l),pos),w.s*.9,w.s*.9);
    },
    pilot(w,l){
      if(w.cool>0)return bot();
      const m=models.get(l);
      const current=encode(w.state);
      if(w.solving!==current){w.route=solve(m,w.state);w.routeAt=0;w.solving=current;}
      const k=w.route?.[w.routeAt];
      if(k===undefined)return bot('action');
      w.routeAt++;
      w.solving=encode(move(m,w.state,k).state);
      return bot(keys[k]);
    },
  });
};
