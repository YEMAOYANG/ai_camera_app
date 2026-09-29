import Image from "next/image";
import type { PictureGuideSegment } from "@/lib/contracts/textbooks";

type Art = PictureGuideSegment["art"];

// A reviewed, original wide composition of this exact published picture.
// Future media revisions continue to use their own art instead of this override.
function wideIllustration(art: Art) {
  return art.sha256 === "d6a8bff5a1540f167473c6e585c8d7e49ef9de2696205854311be1ce5268399f" && art.panel === 3
    ? "/images/storybook/welcome-school-hero.webp" : undefined;
}

export function TextbookPicture({ art, thumbnail = false, landscape = false }: {
  art: Art; thumbnail?: boolean; landscape?: boolean;
}) {
  const wide = landscape ? wideIllustration(art) : undefined;
  return <span className={`textbook-picture${landscape ? " textbook-picture--landscape" : ""}`} data-wide={Boolean(wide)}>
    {wide ? <Image src={wide} alt={art.alt} width={1792} height={896} sizes="(max-width: 760px) 100vw, 1440px" loading="eager" />
      : <span className="textbook-picture-panel"><Image src={art.src} alt={thumbnail ? "" : art.alt} width={1254} height={1254}
        sizes={thumbnail ? "(max-width: 760px) 60vw, 440px" : "(max-width: 760px) 200vw, 1400px"}
        loading={thumbnail ? "lazy" : "eager"} style={{ left: `${art.panel % 2 * -100}%`, top: `${Math.floor(art.panel / 2) * -100}%` }} /></span>}
  </span>;
}
