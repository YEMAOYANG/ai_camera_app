/* eslint-disable @next/next/no-img-element -- Reviewed course assets can be private and must keep cookie authentication. */
// Adapted unchanged from the existing native OpenMAIC picture activity.
/** Original vector illustrations: shared portraits make names optional. */
export type PictureArt = { src: string; alt: string };
export type PictureScene =
  | { art: PictureArt }
  | {
      setting: string;
      skyObject: string;
      ground: string;
      cast: string[];
      speaker?: string;
      listener?: string;
      activity?: string;
    };

const people: Record<string, { shirt: string; hair: string; kind?: string }> = {
  teal: { shirt: '#4b9dac', hair: '#56483e' },
  coral: { shirt: '#d77767', hair: '#584338', kind: 'girl' },
  yellow: { shirt: '#e9b94f', hair: '#443b35', kind: 'cap' },
  dad: { shirt: '#628a65', hair: '#55443d', kind: 'dad' },
  grandpa: { shirt: '#a58a70', hair: '#dad6cc', kind: 'glasses' },
  grandma: { shirt: '#ab87af', hair: '#ded7cf', kind: 'bun' },
  sister: { shirt: '#9c85b7', hair: '#554038', kind: 'girl' },
  mom: { shirt: '#ba805c', hair: '#584238', kind: 'bun' },
  farmer: { shirt: '#689068', hair: '#5d493c', kind: 'hat' },
  teacher: { shirt: '#bf8277', hair: '#57453e', kind: 'glasses' },
  uncle: { shirt: '#7397b0', hair: '#524337', kind: 'dad' },
};

function Person({ id, talking = false }: { id: string; talking?: boolean }) {
  const p = people[id] || people.teal;
  return (
    <g stroke="#514a41" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="0" cy="122" rx="28" ry="5" fill="#52755e" opacity=".13" stroke="none" />
      <path d="M-15 83L-17 116M15 83L17 116" stroke="#4c6471" strokeWidth="13" />
      <path d="M-25 119h15M10 119h15" stroke="#faf6ea" strokeWidth="9" />
      <path
        d="M-23 48Q-38 61-34 81M23 48Q37 57 33 75"
        stroke="#eac2a0"
        strokeWidth="10"
        fill="none"
      />
      <path d="M-20 39Q0 32 20 39L26 86H-26Z" fill={p.shirt} />
      <path d="M-12 41Q0 53 12 41" fill="#fbf5e7" stroke="none" />
      {id === 'teal' && <path d="M-23 64h46M-24 74h48" stroke="#e2f0e7" strokeWidth="5" />}
      {id === 'coral' && (
        <path d="M0 57l3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z" fill="#f9d86e" stroke="none" />
      )}
      {id === 'yellow' && (
        <rect x="-8" y="59" width="16" height="15" rx="3" fill="#fbf1be" stroke="none" />
      )}
      {p.kind === 'girl' && (
        <>
          <ellipse cx="-27" cy="15" rx="9" ry="16" fill={p.hair} />
          <ellipse cx="27" cy="15" rx="9" ry="16" fill={p.hair} />
        </>
      )}
      {p.kind === 'bun' && <circle cy="-19" r="11" fill={p.hair} />}
      <circle r="28" cy="9" fill="#f1c9a8" />
      <path d="M-27 6Q-31-23-3-23Q27-23 28 5L17-1 12-12 4-3-7-10-16 1Z" fill={p.hair} />
      <circle cx="-9" cy="10" r="2.3" fill="#514a41" stroke="none" />
      <circle cx="9" cy="10" r="2.3" fill="#514a41" stroke="none" />
      <ellipse cx="-17" cy="18" rx="5" ry="3" fill="#dc967c" opacity=".65" stroke="none" />
      <ellipse cx="17" cy="18" rx="5" ry="3" fill="#dc967c" opacity=".65" stroke="none" />
      {talking ? (
        <ellipse cy="23" rx="5" ry="6" fill="#815246" stroke="none" />
      ) : (
        <path d="M-5 22Q0 27 5 22" fill="none" strokeWidth="2" />
      )}
      {p.kind === 'glasses' && (
        <g fill="none" strokeWidth="2">
          <circle cx="-10" cy="10" r="8" />
          <circle cx="10" cy="10" r="8" />
          <path d="M-2 10h4" />
        </g>
      )}
      {p.kind === 'dad' && <path d="M-8 22q4-5 8 0 4-5 8 0" strokeWidth="3" />}
      {p.kind === 'hat' && (
        <>
          <path d="M-24-13L-17-32H17L24-13Z" fill="#eac47d" />
          <path d="M-36-12h72" stroke="#ba9250" strokeWidth="9" />
        </>
      )}
      {p.kind === 'cap' && (
        <>
          <path d="M-26-5Q-24-28 0-28Q24-26 26-5Z" fill="#e9b94f" />
          <path d="M-6-5h38" stroke="#c39132" strokeWidth="6" />
        </>
      )}
    </g>
  );
}

function Cloud({ x, y, scale = 1 }: { x: number; y: number; scale?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`} fill="#fffdf4">
      <ellipse cy="10" rx="37" ry="13" />
      <circle cx="-16" r="18" />
      <circle cx="10" cy="-7" r="22" />
      <circle cx="29" cy="5" r="15" />
    </g>
  );
}

function Tree({ x, y, scale = 1 }: { x: number; y: number; scale?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <path
        d="M0 0v85M0 38l-22-22M0 50l24-24"
        stroke="#b89167"
        strokeWidth="12"
        strokeLinecap="round"
      />
      <path
        d="M-52 1Q-62-30-34-45Q-25-80 13-60Q60-65 62-22Q88 24 31 34Q-32 51-52 1"
        fill="#83ad7e"
      />
      <path
        d="M-25-18q21-21 46-5"
        stroke="#adc998"
        strokeWidth="7"
        strokeLinecap="round"
        fill="none"
      />
    </g>
  );
}

function SkyObject({ kind }: { kind: string }) {
  if (kind === 'kite')
    return (
      <g stroke="#755d49" strokeWidth="3" strokeLinejoin="round">
        <path d="M455 45l38 36-29 48-40-35Z" fill="#e38e70" />
        <path d="M455 45l9 84M424 94l69-13" fill="none" />
        <path d="M464 129q25 50-10 64t-11 56" fill="none" />
        <path d="M466 164l-15-5 6 15 12-7 10 11 1-15Z" fill="#e4b95b" />
      </g>
    );
  if (kind === 'rainbow')
    return (
      <g fill="none" strokeWidth="11">
        <path d="M288 137a96 96 0 0 1 192 0" stroke="#d9907f" />
        <path d="M300 137a84 84 0 0 1 168 0" stroke="#e2c66a" />
        <path d="M312 137a72 72 0 0 1 144 0" stroke="#93b99f" />
      </g>
    );
  if (kind === 'balloon')
    return (
      <g>
        <path d="M465 127q-20 47 0 96" fill="none" stroke="#9b8269" strokeWidth="2" />
        <ellipse cx="465" cy="82" rx="35" ry="44" fill="#e29d87" />
        <path d="M454 124l10-10 11 10Z" fill="#cb786b" />
        <path
          d="M450 54q-15 7-12 27"
          stroke="#f4d3b7"
          strokeWidth="7"
          fill="none"
          strokeLinecap="round"
        />
      </g>
    );
  if (kind === 'sun')
    return (
      <g fill="#efca70" stroke="#efca70" strokeWidth="6">
        <circle cx="440" cy="75" r="32" />
        {Array.from({ length: 8 }, (_, i) => (
          <path
            key={i}
            d="M440 29v-9"
            transform={`rotate(${i * 45} 440 75)`}
            strokeLinecap="round"
          />
        ))}
      </g>
    );
  if (kind === 'cloud') return <Cloud x={420} y={85} scale={1.7} />;
  return (
    <g
      transform="translate(420 95)"
      stroke="#526e73"
      strokeWidth="5"
      strokeLinecap="round"
      fill="#fffbed"
    >
      <path d="M-55 9Q-25-34 0 0Q25-34 55 9Q22-9 0 15Q-24-9-55 9" />
      <path d="M-7 10l-6 16 15-9 13 9-7-17" />
    </g>
  );
}

export function PicturePrompt({ scene, label }: { scene: PictureScene; label: string }) {
  if ('art' in scene)
    return (
      <img
        src={scene.art.src}
        alt={scene.art.alt || label}
        draggable={false}
        style={{ width: '100%', maxHeight: '55vh', objectFit: 'contain' }}
      />
    );
  const positions = scene.cast.map((id, i) => ({ id, x: 245 + i * 130 }));
  const speaker = positions.find((p) => p.id === scene.speaker);
  const listener = positions.find((p) => p.id === scene.listener);
  return (
    <svg viewBox="0 0 760 420" role="img" aria-label={label}>
      <rect
        width="760"
        height="420"
        rx="22"
        fill={scene.setting === 'rain' ? '#d9e7e3' : '#d9edf0'}
      />
      <Cloud x={100} y={68} scale={1.15} />
      <Cloud x={650} y={98} scale={0.9} />
      {scene.setting === 'mountains' && (
        <path d="M0 235L150 70 270 219 382 89 574 235 698 125 760 235Z" fill="#9bb9a6" />
      )}
      {scene.setting === 'beach' ? (
        <>
          <path d="M0 201Q190 190 380 208T760 200V340H0Z" fill="#84bfcb" />
          <path d="M0 269q180-24 340 1t420-3v153H0Z" fill="#e7cd97" />
          <path d="M0 255q180-24 340 1t420-3" fill="none" stroke="#f8f6df" strokeWidth="7" />
        </>
      ) : (
        <>
          <path d="M0 214q200-49 390-5t370-1v212H0Z" fill="#afc99a" />
          <path d="M0 315q310-50 760 0v105H0Z" fill="#95b67f" />
          <Tree x={94} y={173} scale={0.9} />
          <Tree x={673} y={183} scale={0.7} />
        </>
      )}
      {scene.setting === 'school' && (
        <g fill="#e6c49b" stroke="#bca787" strokeWidth="3">
          <path d="M55 226V131h130v95Z" />
          <path d="M44 132l76-39 77 39Z" fill="#c78975" />
          <path d="M80 158h23v28H80ZM137 158h23v28h-23Z" fill="#faf6df" />
        </g>
      )}
      {scene.ground === 'track' ? (
        <>
          <path d="M0 291Q300 246 760 291V420H0Z" fill="#cd9c79" />
          <path
            d="M0 336Q300 286 760 336M0 390Q300 333 760 390"
            stroke="#f5e6cb"
            strokeWidth="5"
            fill="none"
          />
        </>
      ) : scene.ground === 'sand' ? null : (
        <path d="M282 237q52 26 4 67t-97 116h332q-148-88-125-127t5-56" fill="#e0caa7" />
      )}
      {scene.ground === 'puddle' && (
        <>
          <ellipse cx="164" cy="355" rx="76" ry="19" fill="#9cc6cc" />
          <path d="M111 353q49-10 102 0" stroke="#e2f0ec" strokeWidth="4" fill="none" />
        </>
      )}
      {scene.ground === 'blanket' && (
        <g stroke="#e9dab7" strokeWidth="5">
          <path d="M490 316l105-9 57 67-118 7Z" fill="#dc9e8b" />
          <path d="M525 313l47 64M560 310l47 64M504 338l112-6M518 359l116-7" />
        </g>
      )}
      {scene.setting === 'field' && (
        <g stroke="#b69a72" strokeWidth="4" fill="none">
          {[0, 1, 2].map((i) => (
            <path key={i} d={`M45 ${330 + i * 24}h116m430 0h112`} />
          ))}
        </g>
      )}
      {scene.setting === 'field' &&
        [85, 132, 624, 680].map((x, i) => (
          <g key={x} transform={`translate(${x} ${320 + (i % 2) * 24})`} fill="#648f59">
            <path d="M0 14V-8" stroke="#648f59" strokeWidth="3" />
            <ellipse cx="-7" cy="-1" rx="10" ry="5" transform="rotate(35)" />
            <ellipse cx="7" cy="-1" rx="10" ry="5" transform="rotate(-35)" />
          </g>
        ))}
      <SkyObject kind={scene.skyObject} />
      {positions.map(({ id, x }) => (
        <g key={id} transform={`translate(${x} 245) scale(1.05)`}>
          <Person id={id} talking={id === scene.speaker} />
        </g>
      ))}
      {speaker && listener && (
        <g stroke="#718d79" strokeWidth="3" fill="none" strokeLinecap="round">
          <path
            d={`M${speaker.x} 168Q${(speaker.x + listener.x) / 2} 140 ${listener.x} 181`}
            strokeDasharray="5 7"
          />
          <path d={`M${listener.x - 8} 174l8 7 7-9`} />
          <g transform={`translate(${speaker.x - 39} 177)`} fill="#fffdf4" stroke="#859982">
            <path d="M14 0h47q14 0 14 14v14q0 14-14 14H39l-12 12v-12H14Q0 42 0 28V14Q0 0 14 0Z" />
            <g stroke="#68816d" fill="none" strokeWidth="3">
              <path d="M29 15v12M38 10v23M47 15v12" />
            </g>
          </g>
        </g>
      )}
      <path
        d="M38 390l3-9 7 8m643 10 4-11 5 8"
        fill="none"
        stroke="#6f9360"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function PictureChoice({ picture }: { picture: string | PictureArt }) {
  if (typeof picture !== 'string')
    return (
      <img
        src={picture.src}
        alt={picture.alt}
        draggable={false}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
      />
    );
  return (
    <svg viewBox="0 0 160 140" aria-hidden="true" focusable="false">
      <rect x="2" y="2" width="156" height="136" rx="16" fill="#f4f3e8" />
      {picture === 'sky' ? (
        <>
          <rect x="2" y="2" width="156" height="136" rx="16" fill="#dceff1" />
          <circle cx="125" cy="30" r="15" fill="#efca70" />
          <Cloud x={49} y={56} scale={0.7} />
          <Cloud x={110} y={100} scale={0.5} />
          <path d="M78 23q9-9 18 0 9-9 18 0" fill="none" stroke="#637f85" strokeWidth="3" />
        </>
      ) : picture === 'earth' ? (
        <>
          <path d="M3 39q70-25 154 0v82q0 17-17 17H20q-17 0-17-17Z" fill="#a9c38d" />
          <path d="M72 31q-35 33-5 52t-5 55h57q-34-34-27-55t-3-52" fill="#d9bc8d" />
          <path
            d="M27 88l3-15 5 13M126 52l4-13 6 13M132 116l4-14 5 12"
            stroke="#5e8456"
            strokeWidth="3"
            fill="none"
          />
        </>
      ) : picture === 'people' ? (
        <>
          {['coral', 'teal', 'yellow'].map((id, i) => (
            <g key={id} transform={`translate(${34 + i * 45} ${i === 1 ? 41 : 49}) scale(.64)`}>
              <Person id={id} />
            </g>
          ))}
        </>
      ) : picture === 'rock' ? (
        <>
          <ellipse cx="80" cy="115" rx="47" ry="8" fill="#d8d9c8" />
          <path
            d="M33 108l10-36 29-18 30 8 24 30-8 20Z"
            fill="#a5aaa1"
            stroke="#747d71"
            strokeWidth="3"
          />
          <path
            d="M47 77l26-16 21 9M99 91l17 14"
            stroke="#d4d8cc"
            strokeWidth="5"
            fill="none"
            strokeLinecap="round"
          />
        </>
      ) : ['above', 'below'].includes(picture) ? (
        <>
          <rect x="3" y="3" width="154" height="58" rx="15" fill="#dceff1" />
          <Cloud x={45} y={27} scale={0.48} />
          <path d="M4 109h152v14q0 13-14 13H17Q4 136 4 123Z" fill="#a9c38d" />
          <g transform="translate(86 55) scale(.62)">
            <Person id="teal" />
          </g>
          <path
            d={
              picture === 'above' ? 'M132 75V32m-11 12 11-12 11 12' : 'M34 76v44m-11-12 11 12 11-12'
            }
            stroke="#c78f36"
            strokeWidth="6"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </>
      ) : (
        <g transform="translate(80 37) scale(.78)">
          <Person id={picture} />
        </g>
      )}
    </svg>
  );
}
