import * as T from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";
import { bookFlight, mix, motionProgress, phase, restingBook, RESTING_BOOK_SCALE, SCHOOL_SUBJECTS, type BagAction, type BagPose, type SchoolSubject } from "./motion-timeline";
import bookLayout from "./book-layout.json";

const MODEL_URL = "/models/schoolbag/schoolbag-v5.glb";
let modelBytes: Promise<ArrayBuffer> | undefined;
function loadModel() {
  modelBytes ??= fetch(MODEL_URL).then(response => {
    if (!response.ok) throw new Error("Schoolbag model unavailable");
    return response.arrayBuffer();
  }).catch(error => { modelBytes = undefined; throw error; });
  return modelBytes.then(bytes => new GLTFLoader().parseAsync(bytes, ""));
}

const palettes = bookLayout.map(book => book.palette);
let coverImages: Promise<(HTMLImageElement | null)[]> | undefined;
function loadCoverImages() {
  coverImages ??= Promise.all(SCHOOL_SUBJECTS.map(subject => new Promise<HTMLImageElement | null>(resolve => {
    const image = new Image();
    const finish = (value: HTMLImageElement | null) => { clearTimeout(timeout); image.onload = image.onerror = null; resolve(value); };
    const timeout = window.setTimeout(() => finish(null), 5000);
    image.onload = () => finish(image); image.onerror = () => finish(null);
    image.src = `/images/schoolbag/covers-v3/${subject}.webp`;
  })));
  return coverImages;
}
function texture(draw: (context: CanvasRenderingContext2D) => void, width = 512, height = 896) {
  const canvas = document.createElement("canvas"); canvas.width = width; canvas.height = height;
  const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("Canvas unavailable");
  draw(ctx);
  const map = new T.CanvasTexture(canvas); map.colorSpace = T.SRGBColorSpace; map.anisotropy = 4; map.flipY = true;
  return map;
}
function coverTexture(index: number, illustration: HTMLImageElement | null) {
  const p = palettes[index];
  return texture(ctx => {
    ctx.fillStyle = "#fcf2dc"; ctx.fillRect(0, 0, 512, 896);
    if (illustration) {
      const width = 896 * illustration.naturalWidth / illustration.naturalHeight;
      ctx.drawImage(illustration, (512 - width) / 2, 0, width, 896);
    } else {
      // Missing artwork must never prevent unlocking or entering a subject.
      ctx.fillStyle = p.pale; ctx.fillRect(0, 250, 512, 646);
      ctx.fillStyle = p.color; ctx.textAlign = "center"; ctx.font = '110px Georgia, serif'; ctx.fillText(p.mark, 270, 570);
    }
    const titleWash = ctx.createLinearGradient(0, 0, 0, 260);
    const titlePaper = index === 1 || index === 2 ? p.pale : "#fcf2dc";
    titleWash.addColorStop(0, titlePaper); titleWash.addColorStop(.68, `${titlePaper}f5`); titleWash.addColorStop(1, `${titlePaper}00`);
    ctx.fillStyle = titleWash; ctx.fillRect(0, 0, 512, 260);
    ctx.fillStyle = p.color; ctx.fillRect(0, 0, 27, 896);
    ctx.fillStyle = "#00000018"; ctx.fillRect(22, 0, 5, 896);
    ctx.fillStyle = "#ffffff36"; ctx.fillRect(30, 0, 2, 896);
    ctx.textAlign = "center"; ctx.fillStyle = p.dark;
    ctx.font = '500 19px -apple-system, "PingFang SC", sans-serif'; ctx.fillText(p.pinyin, 274, 68);
    ctx.font = '600 106px "Kaiti SC", "STKaiti", "PingFang SC", serif'; ctx.fillText(p.title, 274, 182);
    ctx.fillStyle = p.color; ctx.fillRect(27, 811, 485, 85);
    ctx.fillStyle = "#fff5de"; ctx.font = '500 24px "PingFang SC", sans-serif'; ctx.fillText("暖瞳 · 学校课本", 272, 862);
    ctx.strokeStyle = "#dfbf7b"; ctx.lineWidth = 1.5; ctx.strokeRect(42, 19, 451, 776);
  });
}
function pageTexture(index: number, inside: boolean, illustration: HTMLImageElement | null) {
  return texture(ctx => {
    ctx.fillStyle = "#fffaf1"; ctx.fillRect(0, 0, 512, 896);
    const shade = ctx.createLinearGradient(0, 0, 512, 0);
    shade.addColorStop(inside ? 0 : 1, "#b6a18000"); shade.addColorStop(inside ? 1 : 0, "#b6a18035");
    ctx.fillStyle = shade; ctx.fillRect(0, 0, 512, 896);
    ctx.fillStyle = palettes[index].dark; ctx.textAlign = "center";
    ctx.font = '600 66px "Kaiti SC", "STKaiti", "PingFang SC", serif'; ctx.fillText(inside ? palettes[index].title : "一起探索", 256, 210);
    if (illustration) { ctx.save(); ctx.globalAlpha = .9; ctx.drawImage(illustration, 58, 265, 396, 495); ctx.restore(); }
    ctx.fillStyle = palettes[index].color; ctx.beginPath(); ctx.arc(256, 810, 4, 0, Math.PI * 2); ctx.fill();
  });
}
function fabricTexture() {
  return texture(ctx => {
    ctx.fillStyle = "#888"; ctx.fillRect(0, 0, 128, 128);
    for (let y = 0; y < 128; y += 4) for (let x = 0; x < 128; x += 4) {
      ctx.fillStyle = (x + y) % 8 ? "#989898" : "#727272";
      ctx.fillRect(x, y, 3, 1); ctx.fillRect(x + 1, y + 1, 1, 3);
    }
  }, 128, 128);
}

export interface SchoolbagRenderer {
  setPose(pose: BagPose, emphasis?: number): void;
  hover(subject: SchoolSubject | null): void;
  frame(action: BagAction, elapsed: number, subject?: SchoolSubject): void;
  pick(clientX: number, clientY: number): SchoolSubject | null;
  dispose(): void;
}

export async function createSchoolbagRenderer(canvas: HTMLCanvasElement, onError: () => void): Promise<SchoolbagRenderer> {
  const renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap;
  const scene = new T.Scene();
  const camera = new T.PerspectiveCamera(34, 1, .1, 100);
  camera.position.set(2.6, 2.5, 9); camera.lookAt(0, .28, 0);
  scene.add(new T.HemisphereLight("#fff7e9", "#adbbc2", 1.9));
  const key = new T.DirectionalLight("#fff2dc", 3); key.position.set(-3.5, 6, 7); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); Object.assign(key.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4, near: .1, far: 22 });
  key.shadow.bias = -.0005; key.shadow.normalBias = .025; key.shadow.radius = 3; scene.add(key);
  const fill = new T.DirectionalLight("#d2e8fc", 1.4); fill.position.set(5, 3, -2); scene.add(fill);
  // A soft contact shadow instead of a hard, long cast shadow across the UI.
  const shadowMap = texture(ctx => {
    const gradient = ctx.createRadialGradient(128,128,12,128,128,122);
    gradient.addColorStop(0,"#4a39273d"); gradient.addColorStop(.48,"#4a392720"); gradient.addColorStop(1,"#4a392700");
    ctx.fillStyle=gradient; ctx.fillRect(0,0,256,256);
  },256,256);
  const floor = new T.Mesh(new T.PlaneGeometry(4.4,2.3), new T.MeshBasicMaterial({ map: shadowMap, transparent: true, depthWrite: false }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -1.56; scene.add(floor);
  let model: T.Object3D;
  let illustrations: (HTMLImageElement | null)[];
  try { const [gltf, images] = await Promise.all([loadModel(), loadCoverImages()]); model = clone(gltf.scene); illustrations = images; }
  catch (error) { renderer.dispose(); throw error; }
  scene.add(model);
  const weave = fabricTexture(); weave.wrapS = weave.wrapT = T.RepeatWrapping; weave.repeat.set(7, 7); weave.colorSpace = T.NoColorSpace;
  const ownedTextures: T.Texture[] = [weave, shadowMap];
  model.traverse(object => {
    if (!(object instanceof T.Mesh)) return;
    object.castShadow = true; object.receiveShadow = true;
    const material = (object.material as T.MeshStandardMaterial).clone(); object.material = material;
    if (/woven|canvas|lining|webbing|bookcloth/.test(material.name)) { material.bumpMap = weave; material.bumpScale = material.name.startsWith("bookcloth") ? .003 : .009; }
  });
  const part = (name: string) => { const found = model.getObjectByName(name); if (!found) throw new Error(`Missing model part: ${name}`); return found; };
  const bag = part("Backpack"), flap = part("FlapHinge");
  const books = SCHOOL_SUBJECTS.map(subject => part(`Book_${subject}`));
  const covers = SCHOOL_SUBJECTS.map(subject => part(`CoverHinge_${subject}`));
  SCHOOL_SUBJECTS.forEach((subject, i) => {
    for (const [name, map] of [[`CoverArt_${subject}`, coverTexture(i, illustrations[i])], [`InsideArt_${subject}`, pageTexture(i, true, illustrations[i])], [`PageArt_${subject}`, pageTexture(i, false, illustrations[i])]] as const) {
      ownedTextures.push(map); const art = part(name) as T.Mesh;
      (art.material as T.MeshStandardMaterial).map = map; (art.material as T.MeshStandardMaterial).roughness = .88;
    }
  });
  let disposed = false, pose: BagPose = "ready", selected: SchoolSubject | null = null, hoverFrame = 0;
  let flightStart: { action: BagAction; subject: SchoolSubject; elapsed: number; lift: number } | undefined;
  let width = 0, height = 0;
  const draw = () => {
    if (disposed || !canvas.isConnected) return;
    const box = canvas.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return;
    if (width !== box.width || height !== box.height) {
      width = box.width; height = box.height; renderer.setSize(width, height, false); camera.aspect = width / height;
      // Preserve enough horizontal room for both pages on a portrait phone.
      camera.fov = T.MathUtils.radToDeg(2 * Math.atan(Math.tan(T.MathUtils.degToRad(17)) * Math.max(1, .93 / camera.aspect)));
    }
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  };
  const reset = (next: BagPose) => {
    pose = next; bag.position.set(0, 0, 0); bag.scale.setScalar(1); model.rotation.set(0, 0, 0);
    flap.rotation.x = next === "closed" ? 0 : -2.35;
    camera.position.set(2.6, 2.5, 9); camera.zoom = 1.3; camera.lookAt(0, next === "ready" ? .4 : .28, 0); floor.material.opacity = 1;
    books.forEach((book, i) => {
      const home = restingBook(i); book.visible = next === "ready";
      book.position.set(home.x, home.y, home.z); book.rotation.set(0, 0, home.turn); book.scale.setScalar(RESTING_BOOK_SCALE); covers[i].rotation.y = 0;
    });
  };
  const observer = new ResizeObserver(draw); observer.observe(canvas);
  const lose = (event: Event) => { event.preventDefault(); onError(); };
  canvas.addEventListener("webglcontextlost", lose);
  const raycaster = new T.Raycaster();
  reset("ready"); draw();
  return {
    setPose(next, emphasis = 1.3) { cancelAnimationFrame(hoverFrame); flightStart = undefined; reset(next); camera.zoom = emphasis; draw(); },
    hover(subject) {
      if (pose !== "ready") return; selected = subject; cancelAnimationFrame(hoverFrame);
      let count = 0;
      const step = () => {
        let moving = false;
        books.forEach((book, i) => {
          const destination = restingBook(i).y + (selected === SCHOOL_SUBJECTS[i] ? .14 : 0);
          book.position.y = mix(book.position.y, destination, .23);
          if (Math.abs(book.position.y - destination) > .001) moving = true;
        });
        draw(); if (!disposed && moving && count++ < 35) hoverFrame = requestAnimationFrame(step);
      }; step();
    },
    frame(action, elapsed, subject = "chinese") {
      const index = SCHOOL_SUBJECTS.indexOf(subject);
      if (!flightStart || flightStart.action !== action || flightStart.subject !== subject || elapsed < flightStart.elapsed) {
        flightStart = { action, subject, elapsed, lift: action === "open" ? T.MathUtils.clamp(books[index].position.y - restingBook(index).y, 0, .14) : 0 };
      }
      flightStart.elapsed = elapsed;
      cancelAnimationFrame(hoverFrame); reset(action === "pack" ? "closed" : "ready");
      const timing = motionProgress(action, elapsed), t = timing.progress;
      if (action === "pack") {
        flap.rotation.x = -2.35 * timing.opening;
        camera.lookAt(0, mix(.28, .4, timing.opening), 0);
        books.forEach((book, i) => {
          const p = phase(t, .29 + i * .085, .64 + i * .085), home = restingBook(i);
          book.visible = t > .27 + i * .085;
          // Each book descends in its own lane; diagonal flight paths crossed
          // through the two middle books when the schoolbag grew to four.
          book.position.set(home.x, mix(3.9 + i * .2, home.y, p), home.z);
          book.rotation.set(0, 0, home.turn);
        });
      } else {
        const book = books[index], flight = bookFlight(action, elapsed, index, flightStart.lift);
        book.position.set(flight.x, flight.y, flight.z);
        book.rotation.set(flight.rx, flight.ry, flight.rz);
        book.scale.setScalar(flight.scale); covers[index].rotation.y = flight.cover;
        bag.position.y = flight.backdropY;
        books.forEach((other, i) => { if (i !== index) other.position.y += flight.backdropY; });
        floor.material.opacity = Math.max(0, 1 + flight.backdropY / 1.9);
        camera.position.set(mix(2.6, .3, flight.approach), mix(2.5, .8, flight.approach), 9);
        // Follow the initial vertical lift so a taller middle book stays in
        // frame, then settle on the open spread once it is clear of the bag.
        camera.lookAt(0, mix(.4 + .55 * flight.lift, .28, flight.approach), 0);
      }
      // A large idle bag should not become a cropped, oversized full-screen shot.
      camera.zoom = action === "return" ? 1 : mix(1.3, 1, phase(t, 0, .32));
      draw();
    },
    pick(clientX, clientY) {
      const rect = canvas.getBoundingClientRect();
      raycaster.setFromCamera(new T.Vector2((clientX - rect.left) / rect.width * 2 - 1, -(clientY - rect.top) / rect.height * 2 + 1), camera);
      // Include the bag: a book hidden behind cloth must not receive clicks.
      const first = raycaster.intersectObject(model, true).find(hit => hit.object.visible && hit.object.parent?.visible);
      if (!first) return null;
      let node: T.Object3D | null = first.object;
      while (node) { const i = books.indexOf(node); if (i >= 0) return SCHOOL_SUBJECTS[i]; node = node.parent; }
      return null;
    },
    dispose() {
      if (disposed) return; disposed = true; cancelAnimationFrame(hoverFrame); observer.disconnect(); canvas.removeEventListener("webglcontextlost", lose);
      model.traverse(object => { if (object instanceof T.Mesh) { object.geometry.dispose(); (object.material as T.Material).dispose(); } });
      ownedTextures.forEach(map => map.dispose()); floor.geometry.dispose(); floor.material.dispose(); key.shadow.map?.dispose(); renderer.dispose();
    },
  };
}
