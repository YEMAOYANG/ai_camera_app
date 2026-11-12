// Track a moving subject and photograph a particular visual state. A lesson
// supplies the motion settings, state sequence and subject frames. Photos keep
// the actual time, relative offset and frame chosen by the child.
// Optional photoViews uses registered top (1) and side (0) images of the same
// object. Those exact images are used for the live view, goal and saved photos.
K.gameTemplates.shutterScout = config => {
  const {box,text,center,create,bot,sprite,clamp}=Classic;
  const viewsEnabled=Array.isArray(config.levels)&&config.levels.some(l=>l?.photoViews!==undefined);
  const trials=config.observation?.trials??{};
  const trialIds=Object.keys(trials);
  if(viewsEnabled&&trialIds.length!==1)throw new Error('camera views need one observation trial');
  const trial=trialIds[0];
  const viewName=state=>state===1?'top':'side';
  function check(l){
    if(!Array.isArray(l.shots)||l.shots.length<2||l.shots.length>6||
       !l.shots.every(t=>[0,1].includes(t))||!(l.rate>=.55&&l.rate<=1.8)||
       !(l.aperture>=56&&l.aperture<=155)||!(l.range>=88&&l.range<=345))throw new Error('invalid camera level');
    if(viewsEnabled){
      const {top,side}=l.photoViews??{};
      const icons=config.art?.icons??{};
      const valid=(view,id)=>{
        const allowed=trials[trial]?.[view];
        return typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(id)&&
          Array.isArray(allowed)&&allowed.includes(id)&&Object.hasOwn(icons,id)&&
          typeof icons[id]==='string'&&icons[id].trim();
      };
      if(!valid('top',top)||!valid('side',side)||icons[top]===icons[side]||new Set(l.shots).size!==2){
        throw new Error('camera level needs two distinct registered views and both shots');
      }
    }
  }
  function reset(){return {x:640,y:342,t:0,frame:0,delay:0,flash:0,move:0,photos:[],help:false};}
  function subject(w,l){
    const t=w.t*l.rate;
    const phase=.5+.5*Math.cos(t*3.12+.54);
    const state=viewsEnabled?Number(phase>=.54):phase>.72?1:phase<.36?0:-1;
    // Keep the backed subject between the target preview and the photo strip.
    return {x:640+Math.sin(t)*l.range,y:338+Math.sin(t*1.47+.2)*(viewsEnabled?90:132),
      phase,state,angle:Math.sin(t*1.2)*.26};
  }
  function update(w,l,input,dt,fb,imgs){
    w.t+=dt;w.flash=Math.max(0,w.flash-dt);w.move=Math.max(0,w.move-dt);w.delay=Math.max(0,w.delay-dt);
    const dx=(input.held('right')?1:0)-(input.held('left')?1:0);
    const dy=(input.held('down')?1:0)-(input.held('up')?1:0);
    if(dx||dy){
      w.x=clamp(w.x+dx*dt*397,143,1137);w.y=clamp(w.y+dy*dt*342,167,523);
      if(w.move===0){w.move=.19;fb.move();fb.fx(w.x,w.y,'#e3d99e');}
    }
    const target=l.shots[w.photos.length];
    if(w.delay===0&&target!==undefined&&input.press('action')){
      const s=subject(w,l),tol=l.aperture*(w.help?1.35:1);
      const rightPose=s.state===target || (!viewsEnabled&&w.help&&(target?s.phase>.61:s.phase<.46));
      const view=viewsEnabled?l.photoViews[viewName(s.state)]:null;
      if(viewsEnabled){
        const image=imgs.icons.get(view);
        if(!image?.complete||!image.naturalWidth)return;
      }
      w.flash=.14;w.delay=.42;fb.drop();fb.fx(w.x,w.y);
      if(rightPose&&Math.abs(s.x-w.x)<=tol&&Math.abs(s.y-w.y)<=tol*.71){
        const photo={...s,t:w.t,offset:[s.x-w.x,s.y-w.y]};
        if(viewsEnabled)photo.view=view;
        w.photos.push(photo);
        if(viewsEnabled&&w.photos.length===l.shots.length){
          fb.observe(trial,{
            top:w.photos.find(p=>p.state===1).view,
            side:w.photos.find(p=>p.state===0).view,
          });
        }
        fb.award(w.x,w.y);
      }else fb.lost(w.x,w.y);
    }
  }
  function render(c,im,x,y,phase,angle,width){
    if(!im?.complete||!im.naturalWidth){
      c.fillStyle='#cf91b8';K.draw.circle(c,x,y,width*.24);return;
    }
    c.save();c.translate(x,y);c.rotate(angle);c.scale(.35+.65*phase,1);
    sprite(c,im,0,0,width,width*.78);c.restore();
  }
  function draw(w,l,c,imgs){
    const im=imgs.frames[0],s=subject(w,l),needed=l.shots[w.photos.length];
    const tol=l.aperture*(w.help?1.35:1);
    if(viewsEnabled){
      box(c,s.x-90,s.y-77,180,154,18,'#fffdf6');
      sprite(c,imgs.icons.get(l.photoViews[viewName(s.state)]),s.x,s.y,164,144);
    }else render(c,im,s.x,s.y,s.phase,s.angle,153);
    const locked=Math.abs(w.x-s.x)<tol&&Math.abs(w.y-s.y)<tol*.71;
    c.save();c.setLineDash([19,9]);
    K.draw.rr(c,w.x-tol,w.y-tol*.71,tol*2,tol*1.42,12);
    if(viewsEnabled){c.lineWidth=9;c.strokeStyle='#203c34';c.stroke();}
    c.lineWidth=5;c.strokeStyle=locked?'#e2f2a4':'#fff2ce';c.stroke();c.restore();
    if(w.flash>0){c.fillStyle='#fff3cf44';c.fillRect(w.x-tol,w.y-tol*.71,tol*2,tol*1.42);}
    box(c,588,89,104,74,19,'#fff0d0');
    if(viewsEnabled){
      if(needed!==undefined)sprite(c,imgs.icons.get(l.photoViews[viewName(needed)]),640,126,78,61);
    }else render(c,im,640,126,needed===0?.1:1,0,78);
    w.photos.forEach((p,i)=>{
      const x=471+i*98;
      if(viewsEnabled){
        box(c,x,521,90,88,10,'#d9aa69');box(c,x+2,523,86,84,8,'#fffdf6');
        sprite(c,imgs.icons.get(p.view),x+45,565,82,82);
        return;
      }
      box(c,x,536,90,63,10,'#fff6d7');box(c,x+7,543,76,43,7,'#839376');
      c.save();c.beginPath();c.rect(x+7,543,76,43);c.clip();
      render(c,im,x+45+p.offset[0]*.17,565+p.offset[1]*.17,p.phase,p.angle,59);c.restore();
    });
  }
  function finishPhotos(snapshot,imgs){
    const pair=snapshot?.levels.at(-1)?.trials.find(entry=>entry.trialId===trial);
    if(!pair)return null;
    const top=imgs.icons.get(pair.top),side=imgs.icons.get(pair.side);
    if(!top||!side)return null;
    const photos=K.el('section','shutter-observation');
    photos.setAttribute('aria-label','本局观察照片');
    for(const [image,label] of [[top,'从上看'],[side,'从侧面看']]){
      const figure=K.el('figure','',null,photos);
      const picture=K.el('img','',null,figure);
      picture.src=image.src;
      picture.alt='';
      K.el('figcaption','',label,figure);
    }
    return photos;
  }
  return create(config,{backdrop:'#34594d',validate:check,reset,goal:l=>l.shots.length,update,draw,
    controls:['left','right','up','down',['action','◎','按快门']],adapt(w,n){w.help=n>=2;},
    player:(w,l)=>center(w.x,w.y,l.aperture*2,l.aperture*1.42),
    target:(w,l)=>{const s=subject(w,l);return center(s.x,s.y,viewsEnabled?180:154,viewsEnabled?154:108);},
    goalAnchor:viewsEnabled?()=>center(640,126,104,74):undefined,
    finishExtra:viewsEnabled?finishPhotos:undefined,
    pilot(w,l){
      const s=subject(w,l),dx=s.x-w.x,dy=s.y-w.y;
      if(!w.delay&&s.state===l.shots[w.photos.length]&&Math.abs(dx)<l.aperture*.54&&Math.abs(dy)<l.aperture*.4)return bot('action');
      return bot(...(Math.abs(dx)>9?[dx<0?'left':'right']:[]),...(Math.abs(dy)>9?[dy<0?'up':'down']:[]));
    }
  });
};
