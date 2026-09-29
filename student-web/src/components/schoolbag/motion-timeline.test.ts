// Use the actual authored geometry: a same-depth overlap can look harmless in
// DOM tests while its covers flicker and intersect on the GPU.
import { readFileSync } from "node:fs";
import { beforeAll, describe, expect, it } from "vitest";
import { Box3, Euler, Matrix4, Quaternion, Vector3 } from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OBB } from "three/addons/math/OBB.js";
import { bookFlight, MOTION_DURATION, restingBook, RESTING_BOOK_SCALE, SCHOOL_SUBJECTS } from "./motion-timeline";

const localBounds: OBB[] = [];
beforeAll(async () => {
  const bytes = readFileSync("public/models/schoolbag/schoolbag-v5.glb");
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const { scene } = await new GLTFLoader().parseAsync(buffer, "");
  for (const subject of SCHOOL_SUBJECTS) {
    const book = scene.getObjectByName(`Book_${subject}`)!;
    book.position.set(0, 0, 0); book.rotation.set(0, 0, 0); book.scale.setScalar(1);
    localBounds.push(new OBB().fromBox3(new Box3().setFromObject(book)));
  }
});

function bounds(index: number, x: number, y: number, z: number, rx: number, ry: number, rz: number, scale: number) {
  return localBounds[index].clone().applyMatrix4(new Matrix4().compose(new Vector3(x, y, z),
    new Quaternion().setFromEuler(new Euler(rx, ry, rz)), new Vector3(scale, scale, scale)));
}
function restingBounds(index: number, offsetY = 0) {
  const home = restingBook(index);
  return bounds(index, home.x, home.y + offsetY, home.z, 0, 0, home.turn, RESTING_BOOK_SCALE);
}

describe("four-book physical clearance", () => {
  it("keeps every pair separate at rest and while hovering either middle book", () => {
    for (const hover of [-1, 1, 2]) for (let a = 0; a < 4; a++) for (let b = a + 1; b < 4; b++) {
      expect(restingBounds(a, hover === a ? .14 : 0).intersectsOBB(restingBounds(b, hover === b ? .14 : 0)),
        `${SCHOOL_SUBJECTS[a]} / ${SCHOOL_SUBJECTS[b]}`).toBe(false);
    }
  });

  it.each(["open", "return"] as const)("keeps all four books clear throughout %s, including the depth crossing", action => {
    for (let index = 0; index < 4; index++) for (let step = 0; step <= 200; step++) {
      const flight = bookFlight(action, MOTION_DURATION[action] * step / 200, index);
      const moving = bounds(index, flight.x, flight.y, flight.z, flight.rx, flight.ry, flight.rz, flight.scale);
      for (let other = 0; other < 4; other++) if (other !== index) {
        expect(moving.intersectsOBB(restingBounds(other, flight.backdropY)),
          `${action} ${SCHOOL_SUBJECTS[index]} / ${SCHOOL_SUBJECTS[other]} at ${step / 200}`).toBe(false);
      }
      if (Math.abs(flight.cover) > 0) expect(flight.approach).toBe(1);
    }
  });

  it("returns to the exact resting slot and starts extraction from the hovered height", () => {
    for (let index = 0; index < 4; index++) {
      const home = restingBook(index), returned = bookFlight("return", MOTION_DURATION.return, index);
      expect([returned.x, returned.y, returned.z, returned.rz, returned.scale, returned.cover, returned.backdropY])
        .toEqual([home.x, home.y, home.z, home.turn, RESTING_BOOK_SCALE, -0, -0]);
      expect(bookFlight("open", 0, index, .14).y).toBeCloseTo(home.y + .14);
    }
  });
});
