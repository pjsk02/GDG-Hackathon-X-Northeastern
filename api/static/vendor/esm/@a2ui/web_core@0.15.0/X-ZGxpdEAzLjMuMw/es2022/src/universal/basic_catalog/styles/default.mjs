/* esm.sh - @a2ui/web_core@0.15.0/src/universal/basic_catalog/styles/default */
var l=`
  :where(:root) {
    color-scheme: light dark;
  }

  :where(.a2ui-dark) {
    color-scheme: dark;
  }

  :where(.a2ui-light) {
    color-scheme: light;
  }

  :where(:root), :where(.a2ui-dark), :where(.a2ui-light) {
    --a2ui-color-background: light-dark(#eee, #111);
    --a2ui-color-on-background: light-dark(#333, #eee);

    --a2ui-color-surface: light-dark(
      color-mix(in oklab, var(--a2ui-color-background) 85%, white),
      color-mix(in oklab, var(--a2ui-color-background) 95%, white)
    );
    --a2ui-color-on-surface: light-dark(#333, #eee);

    --a2ui-color-primary: #17e;
    --a2ui-color-primary-light: ${i("light",{colorVar:"--a2ui-color-primary"})};
    --a2ui-color-primary-dark: ${i("dark",{colorVar:"--a2ui-color-primary"})};
    --a2ui-color-primary-hover: ${i("hover",{darkVar:"--a2ui-color-primary-dark",lightVar:"--a2ui-color-primary-light"})};
    --a2ui-color-on-primary: #fff;

    --a2ui-color-secondary: light-dark(#ddd, #333);
    --a2ui-color-secondary-light: ${i("light",{colorVar:"--a2ui-color-secondary"})};
    --a2ui-color-secondary-dark: ${i("dark",{colorVar:"--a2ui-color-secondary",percentage:95})};
    --a2ui-color-secondary-hover: ${i("hover",{darkVar:"--a2ui-color-secondary-dark",lightVar:"--a2ui-color-secondary-light"})};
    --a2ui-color-on-secondary: light-dark(#333, #eee);

    --a2ui-border-radius: 0.25rem;
    --a2ui-color-border: light-dark(#ccc, #444);
    --a2ui-border-width: 1px;
    --a2ui-border: 1px solid var(--a2ui-color-border, #ccc);

    --a2ui-font-family-title: inherit;
    --a2ui-font-family-monospace: monospace;
    --a2ui-color-input: light-dark(#fff, #2a2a2a);
    --a2ui-color-on-input: light-dark(#333, #eee);

    --a2ui-grid-base: 0.5rem;
    --a2ui-spacing-xs: calc(var(--a2ui-spacing-s) / 2);
    --a2ui-spacing-s: calc(var(--a2ui-spacing-m) / 2);
    --a2ui-spacing-m: var(--a2ui-grid-base);
    --a2ui-spacing-l: calc(var(--a2ui-spacing-m) * 2);
    --a2ui-spacing-xl: calc(var(--a2ui-spacing-l) * 2);

    --a2ui-font-size: 1rem;
    --a2ui-font-scale: 1.2;
    --a2ui-font-size-xs: calc(var(--a2ui-font-size-s) / var(--a2ui-font-scale));
    --a2ui-font-size-s: calc(var(--a2ui-font-size-m) / var(--a2ui-font-scale));
    --a2ui-font-size-m: var(--a2ui-font-size);
    --a2ui-font-size-l: calc(var(--a2ui-font-size-m) * var(--a2ui-font-scale));
    --a2ui-font-size-xl: calc(var(--a2ui-font-size-l) * var(--a2ui-font-scale));
    --a2ui-font-size-2xl: calc(var(--a2ui-font-size-xl) * var(--a2ui-font-scale));

    --a2ui-line-height-headings: 1.2;
    --a2ui-line-height-body: 1.5;
  }
`,c;function t(){return c||(c=new CSSStyleSheet,c.replaceSync(l)),c}function u(o){if(typeof document>"u")return;let r=t(),a=typeof document<"u"?document.adoptedStyleSheets:null;if(a&&typeof a.includes=="function"&&!a.includes(r))try{document.adoptedStyleSheets=[...a,r]}catch{}if(o&&o!==document){let e=o.adoptedStyleSheets;if(e&&typeof e.includes=="function"&&!e.includes(r))try{o.adoptedStyleSheets=[...e,r]}catch{}}}function i(o,r){switch(o){case"light":{let a=r;return`color-mix(in oklab, var(${a.colorVar}) ${a.percentage??85}%, ${a.mixColor??"white"})`}case"dark":{let a=r;return`color-mix(in oklab, var(${a.colorVar}) ${a.percentage??85}%, ${a.mixColor??"black"})`}case"hover":{let a=r;return`light-dark(var(${a.darkVar}), var(${a.lightVar}))`}}}export{i as computeColorVariant,u as injectBasicCatalogStyles};
//# sourceMappingURL=default.mjs.map