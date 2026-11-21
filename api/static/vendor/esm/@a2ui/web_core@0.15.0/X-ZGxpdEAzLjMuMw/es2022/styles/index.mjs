/* esm.sh - @a2ui/web_core@0.15.0/styles/index */
var j=`
  &:not([disabled]) {
    cursor: pointer;
    opacity: var(--opacity, 0);
    transition: opacity var(--speed, 0.2s) cubic-bezier(0, 0, 0.3, 1);

    &:hover,
    &:focus {
      opacity: 1;
    }
  }`,m=`
  ${new Array(21).fill(0).map((e,t)=>`.behavior-ho-${t*5} {
          --opacity: ${t/20};
          ${j}
        }`).join(`
`)}

  .behavior-o-s {
    overflow: scroll;
  }

  .behavior-o-a {
    overflow: auto;
  }

  .behavior-o-h {
    overflow: hidden;
  }

  .behavior-sw-n {
    scrollbar-width: none;
  }
`;var $=`
  ${new Array(25).fill(0).map((e,t)=>`
        .border-bw-${t} { border-width: ${t}px; }
        .border-btw-${t} { border-top-width: ${t}px; }
        .border-bbw-${t} { border-bottom-width: ${t}px; }
        .border-blw-${t} { border-left-width: ${t}px; }
        .border-brw-${t} { border-right-width: ${t}px; }

        .border-ow-${t} { outline-width: ${t}px; }
        .border-br-${t} { border-radius: ${t*4}px; overflow: hidden;}`).join(`
`)}

  .border-br-50pc {
    border-radius: 50%;
  }

  .border-bs-s {
    border-style: solid;
  }
`;var g=[0,5,10,15,20,25,30,35,40,50,60,70,80,90,95,98,99,100];function R(...e){let t={};for(let o of e)for(let[r,a]of Object.entries(o)){let l=r.split("-").with(-1,"").join("-"),y=Object.keys(t).filter(s=>s.startsWith(l));for(let s of y)delete t[s];t[r]=a}return t}function F(e,t,...o){let r=structuredClone(e);for(let a of o)for(let l of Object.keys(a)){let y=l.split("-").with(-1,"").join("-");for(let[s,p]of Object.entries(r)){if(t.includes(s))continue;let u=!1;for(let h=0;h<p.length;h++)p[h].startsWith(y)&&(u=!0,p[h]=l);u||p.push(l)}}return r}function G(e){let t={};for(let o of Object.values(e))for(let[r,a]of Object.entries(o)){let l=i(r);t[l]=a}return t}function i(e){return e.startsWith("nv")?`--nv-${e.slice(2)}`:`--${e[0]}-${e.slice(1)}`}var c=e=>`
    ${e.map(t=>{let o=d(t);return`.color-bc-${t} { border-color: light-dark(var(${i(t)}), var(${i(o)})); }`}).join(`
`)}

    ${e.map(t=>{let o=d(t),r=[`.color-bgc-${t} { background-color: light-dark(var(${i(t)}), var(${i(o)})); }`,`.color-bbgc-${t}::backdrop { background-color: light-dark(var(${i(t)}), var(${i(o)})); }`];for(let a=.1;a<1;a+=.1)r.push(`.color-bbgc-${t}_${(a*100).toFixed(0)}::backdrop {
            background-color: light-dark(oklch(from var(${i(t)}) l c h / calc(alpha * ${a.toFixed(1)})), oklch(from var(${i(o)}) l c h / calc(alpha * ${a.toFixed(1)})) );
          }
        `);return r.join(`
`)}).join(`
`)}

  ${e.map(t=>{let o=d(t);return`.color-c-${t} { color: light-dark(var(${i(t)}), var(${i(o)})); }`}).join(`
`)}
  `,d=e=>{let t=e.match(/^([a-z]+)(\d+)$/);if(!t)return e;let[,o,r]=t,l=100-parseInt(r,10),y=g.reduce((s,p)=>Math.abs(p-l)<Math.abs(s-l)?p:s);return`${o}${y}`},f=e=>g.map(t=>`${e}${t}`),b=[c(f("p")),c(f("s")),c(f("t")),c(f("n")),c(f("nv")),c(f("e")),`
    .color-bgc-transparent {
      background-color: transparent;
    }

    :host {
      color-scheme: var(--color-scheme);
    }
  `];var x=`
  .g-icon {
    font-family: "Material Symbols Outlined", "Google Symbols";
    font-weight: normal;
    font-style: normal;
    font-display: optional;
    font-size: 24px;
    width: 1em;
    height: 1em;
    user-select: none;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    font-feature-settings: "liga";
    -webkit-font-feature-settings: "liga";
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    -moz-osx-font-smoothing: grayscale;
    overflow: hidden;

    font-variation-settings: "FILL" 0, "wght" 300, "GRAD" 0, "opsz" 48,
      "ROND" 100;

    &.filled {
      font-variation-settings: "FILL" 1, "wght" 300, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }

    &.filled-heavy {
      font-variation-settings: "FILL" 1, "wght" 700, "GRAD" 0, "opsz" 48,
        "ROND" 100;
    }
  }
`;var w=`
  :host {
    ${new Array(16).fill(0).map((e,t)=>`--g-${t+1}: ${(t+1)*4}px;`).join(`
`)}
  }

  ${new Array(49).fill(0).map((e,t)=>{let o=t-24,r=o<0?`n${Math.abs(o)}`:o.toString();return`
        .layout-p-${r} { --padding: ${o*4}px; padding: var(--padding); }
        .layout-pt-${r} { padding-top: ${o*4}px; }
        .layout-pr-${r} { padding-right: ${o*4}px; }
        .layout-pb-${r} { padding-bottom: ${o*4}px; }
        .layout-pl-${r} { padding-left: ${o*4}px; }

        .layout-m-${r} { --margin: ${o*4}px; margin: var(--margin); }
        .layout-mt-${r} { margin-top: ${o*4}px; }
        .layout-mr-${r} { margin-right: ${o*4}px; }
        .layout-mb-${r} { margin-bottom: ${o*4}px; }
        .layout-ml-${r} { margin-left: ${o*4}px; }

        .layout-t-${r} { top: ${o*4}px; }
        .layout-r-${r} { right: ${o*4}px; }
        .layout-b-${r} { bottom: ${o*4}px; }
        .layout-l-${r} { left: ${o*4}px; }`}).join(`
`)}

  ${new Array(25).fill(0).map((e,t)=>`
        .layout-g-${t} { gap: ${t*4}px; }`).join(`
`)}

  ${new Array(8).fill(0).map((e,t)=>`
        .layout-grd-col${t+1} { grid-template-columns: ${"1fr ".repeat(t+1).trim()}; }`).join(`
`)}

  .layout-pos-a {
    position: absolute;
  }

  .layout-pos-rel {
    position: relative;
  }

  .layout-dsp-none {
    display: none;
  }

  .layout-dsp-block {
    display: block;
  }

  .layout-dsp-grid {
    display: grid;
  }

  .layout-dsp-iflex {
    display: inline-flex;
  }

  .layout-dsp-flexvert {
    display: flex;
    flex-direction: column;
  }

  .layout-dsp-flexhor {
    display: flex;
    flex-direction: row;
  }

  .layout-fw-w {
    flex-wrap: wrap;
  }

  .layout-al-fs {
    align-items: start;
  }

  .layout-al-fe {
    align-items: end;
  }

  .layout-al-c {
    align-items: center;
  }

  .layout-as-n {
    align-self: normal;
  }

  .layout-js-c {
    justify-self: center;
  }

  .layout-sp-c {
    justify-content: center;
  }

  .layout-sp-ev {
    justify-content: space-evenly;
  }

  .layout-sp-bt {
    justify-content: space-between;
  }

  .layout-sp-s {
    justify-content: start;
  }

  .layout-sp-e {
    justify-content: end;
  }

  .layout-ji-e {
    justify-items: end;
  }

  .layout-r-none {
    resize: none;
  }

  .layout-fs-c {
    field-sizing: content;
  }

  .layout-fs-n {
    field-sizing: none;
  }

  .layout-flx-0 {
    flex: 0 0 auto;
  }

  .layout-flx-1 {
    flex: 1 0 auto;
  }

  .layout-c-s {
    contain: strict;
  }

  /** Widths **/

  ${new Array(10).fill(0).map((e,t)=>{let o=(t+1)*10;return`.layout-w-${o} { width: ${o}%; max-width: ${o}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((e,t)=>{let o=t*4;return`.layout-wp-${t} { width: ${o}px; }`}).join(`
`)}

  /** Heights **/

  ${new Array(10).fill(0).map((e,t)=>{let o=(t+1)*10;return`.layout-h-${o} { height: ${o}%; }`}).join(`
`)}

  ${new Array(16).fill(0).map((e,t)=>{let o=t*4;return`.layout-hp-${t} { height: ${o}px; }`}).join(`
`)}

  .layout-el-cv {
    & img,
    & video {
      width: 100%;
      height: 100%;
      object-fit: cover;
      margin: 0;
    }
  }

  .layout-ar-sq {
    aspect-ratio: 1 / 1;
  }

  .layout-ex-fb {
    margin: calc(var(--padding) * -1) 0 0 calc(var(--padding) * -1);
    width: calc(100% + var(--padding) * 2);
    height: calc(100% + var(--padding) * 2);
  }
`;var v=`
  ${new Array(21).fill(0).map((e,t)=>`.opacity-el-${t*5} { opacity: ${t/20}; }`).join(`
`)}
`;var z=`
  :host {
    --default-font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    --default-font-family-mono: "Courier New", Courier, monospace;
  }

  .typography-f-s {
    font-family: var(--font-family, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-f-sf {
    font-family: var(--font-family-flex, var(--default-font-family));
    font-optical-sizing: auto;
  }

  .typography-f-c {
    font-family: var(--font-family-mono, var(--default-font-family));
    font-optical-sizing: auto;
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0;
  }

  .typography-v-r {
    font-variation-settings: "slnt" 0, "wdth" 100, "GRAD" 0, "ROND" 100;
  }

  .typography-ta-s {
    text-align: start;
  }

  .typography-ta-c {
    text-align: center;
  }

  .typography-fs-n {
    font-style: normal;
  }

  .typography-fs-i {
    font-style: italic;
  }

  .typography-sz-ls {
    font-size: 11px;
    line-height: 16px;
  }

  .typography-sz-lm {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-ll {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bs {
    font-size: 12px;
    line-height: 16px;
  }

  .typography-sz-bm {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-bl {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-ts {
    font-size: 14px;
    line-height: 20px;
  }

  .typography-sz-tm {
    font-size: 16px;
    line-height: 24px;
  }

  .typography-sz-tl {
    font-size: 22px;
    line-height: 28px;
  }

  .typography-sz-hs {
    font-size: 24px;
    line-height: 32px;
  }

  .typography-sz-hm {
    font-size: 28px;
    line-height: 36px;
  }

  .typography-sz-hl {
    font-size: 32px;
    line-height: 40px;
  }

  .typography-sz-ds {
    font-size: 36px;
    line-height: 44px;
  }

  .typography-sz-dm {
    font-size: 45px;
    line-height: 52px;
  }

  .typography-sz-dl {
    font-size: 57px;
    line-height: 64px;
  }

  .typography-ws-p {
    white-space: pre-line;
  }

  .typography-ws-nw {
    white-space: nowrap;
  }

  .typography-td-none {
    text-decoration: none;
  }

  /** Weights **/

  ${new Array(9).fill(0).map((e,t)=>{let o=(t+1)*100;return`.typography-w-${o} { font-weight: ${o}; }`}).join(`
`)}
`;var U=[m,$,b,x,w,v,z].flat(1/0).join(`
`);export{F as appendToAll,G as createThemeStyles,R as merge,U as structuralStyles,i as toProp};
//# sourceMappingURL=index.mjs.map