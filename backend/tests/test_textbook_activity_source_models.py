"""Actual finite mesh states; source/grade admission is separately frozen in IR."""
from copy import deepcopy
import json
import unittest

from tests import test_textbook_activity_compiler as fixtures
from content.textbook_activity_source_models import SUPPORTED
from services.textbook_activity_compiler import model_scene


class SourceSemanticMeshes(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DeterministicActivityCompiler()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ir = self.fixture.ir()

    def test_eight_actual_entity_families_first_action_three_states_and_end_gate(self):
        for key, states in SUPPORTED.items():
            scene = deepcopy(self.ir["scenes"][2])
            scene["modelAdapterKey"] = key
            scene["states"] = [{"sceneStateId": state, "assetId": asset, "observationCueId": "model_"+asset}
                               for state, asset in zip(states, ("one", "three", "five"))]
            script = 'const states='+json.dumps(states)+';\n'+r'''
const snapshots=[run('JSON.stringify({meshes,poses,teachingState})')];assert.ok(draws.length>0);
for(const [i,id]of states.entries()){
 const before=calls.length;run('applyModel('+JSON.stringify(id)+')');await tick();assert.equal(calls.length,before);snapshots.push(run('JSON.stringify({meshes,poses,teachingState})'));assert.notEqual(snapshots[i+1],snapshots[i]);frame();frame();await tick();assert.equal(run('visited.size'),i);await ended();assert.equal(run('visited.size'),i+1);
 assert.ok(run('Object.values(geometries).every(g=>g.every(Number.isFinite))'));
}
assert.equal(new Set(snapshots).size,4);assert.equal(document.getElementById('finish').disabled,false);const old=run('JSON.stringify(poses.focus)');run('manipulate(.25,Math.PI/8)');assert.notEqual(run('JSON.stringify(poses.focus)'),old);assert.equal(run('commitState("unknown")'),false);
'''
            if key == "five_counters_join_remove":
                script += r'''
for(const id of states){run('commitState('+JSON.stringify(id)+')');const s=run('teachingState');assert.equal(s.totalCount,5);assert.equal(s.items.length,5);assert.equal(s.sourceCount+s.activeCount+s.removedCount,5);assert.equal(s.items.filter(x=>x.onMat).length,s.activeCount);assert.equal(s.operation.after,s.activeCount);assert.equal(run('meshes.filter(m=>m.semanticKind&&m.semanticKind.startsWith("counter-")).length'),5);}
run('commitState("five_remove_two")');assert.equal(run('teachingState.operation.before-teachingState.operation.remove'),3);assert.equal(run('teachingState.sourceCount'),0);assert.equal(run('teachingState.removedCount'),2);assert.ok(run('teachingState.items.filter(x=>x.area==="removed").every(x=>x.x>1.5)'));
run('resetGeometry()');assert.ok(run('teachingState.items.every(x=>x.area==="source"&&Math.abs(x.x+2)+.14<=.55&&Math.abs(x.z)+.14<=.525)'));
'''
            if key == "chinese_chick_duck_positions_scene":
                script += r'''
run('commitState("chicken_ahead")');assert.ok(run('teachingState.chicken.x>teachingState.duck.x'));run('commitState("duck_ahead")');assert.ok(run('teachingState.duck.x>teachingState.chicken.x'));run('commitState("side_by_side")');assert.equal(run('teachingState.chicken.x'),run('teachingState.duck.x'));assert.notEqual(run('teachingState.chicken.z'),run('teachingState.duck.z'));assert.equal(run('teachingState.groundOnly'),true);assert.equal(run('teachingState.heading'),'right');assert.ok(run('meshes.filter(m=>m.semanticKind==="duck").length')>10);assert.ok(run('meshes.filter(m=>m.semanticKind==="chick").length')>10);assert.equal(run('meshes.some(m=>m.semanticKind==="pond")'),false);
assert.ok(run('Math.abs(teachingState.chicken.z-teachingState.duck.z)*Math.sin(.6)')>1.3);assert.ok(run('meshes.filter(m=>["duck","chick"].includes(m.semanticKind)).every(m=>Math.abs(m.local[14])+Math.max(m.local[8],m.local[10])/2<1.7)'));
assert.equal(run('meshes.filter(m=>m.semanticKind==="chick"&&m.semanticPiece==="chick-comb").length'),3);
'''
            if key == "equal_groups_array_scene":
                script += r'''
for(const [i,id]of states.entries()){run('commitState('+JSON.stringify(id)+')');const s=run('teachingState');assert.equal(s.totalCount,8);assert.equal(s.sourceCount+s.activeCount,8);assert.equal(s.rows,[2,2,4][i]);assert.equal(s.cols,[3,4,2][i]);assert.equal(s.rows*s.cols,s.activeCount);assert.equal(s.items.filter(x=>x.onBoard).length,s.activeCount);}
'''
            if key in {"english_schoolthings_semantic_scene", "english_food_requests_semantic_scene", "chinese_spring_observation_scene", "plant_habitats_observation_scene"}:
                script += r'''
for(const id of states){run('commitState('+JSON.stringify(id)+')');const s=run('teachingState');const key=id.endsWith('_near')?id.slice(0,-5):id;assert.equal(s.selected,key);assert.ok(s.positions[key][2]>.8);assert.ok(run('meshes.some(m=>m.semanticKind==='+JSON.stringify(key)+')'));}
'''
            if key == "english_food_requests_semantic_scene":
                script += r'''
assert.equal(run('meshes.some(m=>m.semanticKind==="rice")'),false);const white=run('meshes.filter(m=>m.semanticKind==="milk").some(m=>m.color[0]>.9&&m.color[1]>.9)');assert.equal(white,true);
'''
            if key == "chinese_spring_observation_scene":
                script += r'''
run('commitState("flowers_near")');const centers=run('meshes.filter(m=>m.semanticKind==="flowers"&&m.semanticPiece==="flower-center")'),petals=run('meshes.filter(m=>m.semanticKind==="flowers"&&m.semanticPiece==="flower-petal")');assert.equal(centers.length,3);assert.equal(new Set(centers.map(m=>m.local[12])).size,3);assert.equal(petals.length,15);assert.equal(new Set(petals.map(m=>JSON.stringify(m.color))).size,3);for(const c of centers)assert.equal(petals.filter(m=>Math.abs(m.local[12]-c.local[12])<.25).length,5);
'''
            if key == "water_container_observation_scene":
                script += r'''
const volumes=[];for(const id of states){run('commitState('+JSON.stringify(id)+')');assert.equal(run('teachingState.waterContainer'),id);assert.equal(run('meshes.filter(m=>m.semanticKind==="model-water").length'),1);volumes.push(run('(()=>{const m=meshes.find(m=>m.semanticKind==="model-water");return m.local[0]*m.local[5]*m.local[10];})()'));}assert.ok(Math.max(...volumes)-Math.min(...volumes)<1e-6);assert.equal(run('teachingState.notExperimentEvidence'),true);
assert.equal(run('teachingState.transparentOutline'),true);assert.equal(run('meshes.some(m=>["cup","dish","bottle"].includes(m.semanticKind)&&["cup","dish","bottle","cylinder"].includes(m.shape))'),false);for(const key of states)assert.ok(run('meshes.filter(m=>m.semanticKind==='+JSON.stringify(key)+').length')>=10);
for(const key of states){run('commitState('+JSON.stringify(key)+')');const water=run('meshes.find(m=>m.semanticKind==="model-water")'),profile=run('teachingState.vesselProfiles')[key];for(const y of [water.local[13]-water.local[5]/2,water.local[13]+water.local[5]/2]){const j=profile.findIndex((p,i)=>i<profile.length-1&&y>=p[1]&&y<=profile[i+1][1]);assert.ok(j>=0);const [r0,y0]=profile[j],[r1,y1]=profile[j+1],wall=r0+(r1-r0)*(y-y0)/(y1-y0);assert.ok(water.local[0]/2<wall-.012);}}
'''
            if key == "plant_habitats_observation_scene":
                script += r'''
run('commitState("grassland")');const rocks=run('meshes.filter(m=>m.semanticKind==="grassland"&&m.semanticPiece==="grassland-rock")');assert.equal(rocks.length,2);assert.ok(rocks.every(m=>m.shape==="sphere"&&m.color[0]>.4&&m.color[0]<.7));assert.ok(rocks.every(m=>m.local[12]>.1&&m.local[14]>1.3));assert.ok(run('meshes.some(m=>m.semanticKind==="grassland"&&m.semanticPiece==="grass-leaf")'));
'''
            if key == "fruit_shape_observation_scene":
                script += r'''
for(const id of states){run('commitState('+JSON.stringify(id)+')');const key=id.slice(0,-5);assert.equal(run('teachingState.selected'),key);assert.ok(run('teachingState.positions')[key][2]>.9);assert.ok(run('meshes.some(m=>m.semanticKind==='+JSON.stringify(key)+')'));}
assert.ok(run('meshes.some(m=>m.semanticPiece==="pear-neck")'));assert.ok(run('meshes.filter(m=>m.semanticPiece==="orange-peel-mark").length')>=12);assert.equal(run('teachingState.notTasteOrExperimentEvidence'),true);
'''
            with self.subTest(family=key):
                self.fixture.execute(model_scene(scene, self.ir["assets"]), script, model=True)

    def test_source_family_requires_explicit_frozen_state_pictures(self):
        scene = deepcopy(self.ir["scenes"][2])
        scene["modelAdapterKey"] = "english_schoolthings_semantic_scene"
        scene["states"][0].pop("assetId")
        with self.assertRaisesRegex(ValueError, "state_pictures_required"):
            model_scene(scene, self.ir["assets"])


if __name__ == "__main__":
    unittest.main()
