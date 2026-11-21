/* esm.sh - @a2ui/web_core@0.15.0/src/universal/basic_catalog/components/index */
import{html as bi,nothing as gi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{A2uiLitElement as xi}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/universal.mjs";import{injectBasicCatalogStyles as yi,computeColorVariant as G}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/styles/default.mjs";import{isValidCssColor as $i}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/theme.mjs";var n=class extends xi{createRenderRoot(){return this}connectedCallback(){super.connectedCallback(),yi()}willUpdate(i){super.willUpdate(i);let e=this.controller?.props;e&&e.weight!==void 0?this.style.flex=String(e.weight):this.style.removeProperty("flex");let a=this.context?.theme?.primaryColor;typeof a=="string"&&$i(a)?(this.style.setProperty("--a2ui-color-primary",a),this.style.setProperty("--a2ui-color-primary-light",G("light",{colorVar:"--a2ui-color-primary"})),this.style.setProperty("--a2ui-color-primary-dark",G("dark",{colorVar:"--a2ui-color-primary"})),this.style.setProperty("--a2ui-color-primary-hover",G("hover",{darkVar:"--a2ui-color-primary-dark",lightVar:"--a2ui-color-primary-light"}))):(this.style.removeProperty("--a2ui-color-primary"),this.style.removeProperty("--a2ui-color-primary-light"),this.style.removeProperty("--a2ui-color-primary-dark"),this.style.removeProperty("--a2ui-color-primary-hover")),this.applyAccessibilityAttributes(e?.accessibility)}renderValidationErrors(i){return i?.isValid===!1&&i.validationErrors?.length?i.validationErrors.map(e=>bi`<div class="a2ui-error-message">${e}</div>`):gi}applyAccessibilityAttributes(i){this.hasAttributeValue(i?.label)?this.setAttribute("aria-label",String(i?.label)):this.removeAttribute("aria-label"),this.hasAttributeValue(i?.description)?this.setAttribute("aria-description",String(i?.description)):this.removeAttribute("aria-description"),this.hasAttributeValue(i?.live)?this.setAttribute("aria-live",String(i?.live)):this.removeAttribute("aria-live"),typeof i?.hidden=="boolean"?this.setAttribute("aria-hidden",String(i.hidden)):this.removeAttribute("aria-hidden")}hasAttributeValue(i){return i!=null&&i!==""}};import{html as ii,nothing as J,css as wi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{sanitizeMediaUrl as ki}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/common/sanitize_media_url.mjs";var $=class extends n{render(){let i=this.controller.props;if(!i)return J;let e=ki(i.url);return ii`
      <div class="a2ui-audio-player">
        ${i.description?ii`<div class="a2ui-audio-description">${i.description}</div>`:J}
        <audio src=${e??J} controls class="a2ui-audio">
          Your browser does not support the audio tag.
        </audio>
      </div>
    `}};$.tagName="a2ui-audioplayer";$.styles=wi`
    .a2ui-audio-player {
      display: flex;
      flex-direction: column;
      gap: var(--a2ui-spacing-xs, 0.25rem);
      background: var(--a2ui-audioplayer-background, transparent);
      border-radius: var(--a2ui-audioplayer-border-radius, 0);
      padding: var(--a2ui-audioplayer-padding, 0);
      width: 100%;
    }
    .a2ui-audio-description {
      font-size: var(--a2ui-font-size-s, 0.875rem);
      color: var(
        --a2ui-audioplayer-description-color,
        var(--a2ui-text-caption-color, light-dark(#666, #aaa))
      );
    }
    .a2ui-audio {
      width: 100%;
    }
  `;import{html as ei,nothing as ai,css as zi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{classMap as Ai}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var w=class extends n{render(){let i=this.controller.props;if(!i)return ai;let e=i.isValid===!1,r={"a2ui-button":!0,["a2ui-button-"+(i.variant??"default")]:!0};return ei`
      <button
        type="button"
        class=${Ai(r)}
        @click=${()=>{e||i.action?.()}}
        ?disabled=${e}
      >
        ${i.child?ei`${this.renderNode(i.child)}`:ai}
      </button>
    `}};w.tagName="a2ui-basic-button";w.styles=zi`
    .a2ui-button {
      padding: var(
        --a2ui-button-padding,
        var(--a2ui-spacing-m, 0.5rem) var(--a2ui-spacing-l, 1rem)
      );
      border-radius: var(--a2ui-button-border-radius, var(--a2ui-spacing-s, 0.25rem));
      border: var(
        --a2ui-button-border,
        var(--a2ui-border-width, 1px) solid var(--a2ui-color-border, #ccc)
      );
      cursor: pointer;
      margin: var(--a2ui-button-margin, var(--a2ui-spacing-m, 0.5rem));
      background: var(--a2ui-button-background, var(--a2ui-color-surface, #fff));
      box-shadow: var(--a2ui-button-box-shadow, none);
      font-weight: var(--a2ui-button-font-weight, normal);
      --_a2ui-text-margin: 0;
      --_a2ui-text-color: var(--a2ui-color-on-secondary, #333);
      color: var(--_a2ui-text-color);
    }
    .a2ui-button:hover {
      background-color: var(--a2ui-color-secondary-hover, #ddd);
    }
    .a2ui-button.a2ui-button-primary {
      background: var(--a2ui-color-primary, #17e);
      --_a2ui-text-color: var(--a2ui-color-on-primary, #fff);
      color: var(--_a2ui-text-color);
      border: none;
    }
    .a2ui-button.a2ui-button-primary:hover {
      background-color: var(--a2ui-color-primary-hover, #fbd);
    }
    .a2ui-button.a2ui-button-borderless {
      background: none;
      border: none;
      padding: 0;
      color: var(--a2ui-color-primary, #17e);
    }
    .a2ui-button:disabled {
      cursor: not-allowed;
      opacity: 0.5;
    }
  `;import{html as Ci,nothing as ti,css as Pi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";var k=class extends n{render(){let i=this.controller.props;return i?Ci`
      <div class="a2ui-card">${i.child?this.renderNode(i.child):ti}</div>
    `:ti}};k.tagName="a2ui-card";k.styles=Pi`
    .a2ui-card {
      padding: var(--a2ui-card-padding, var(--a2ui-spacing-m, 16px));
      border-radius: var(--a2ui-card-border-radius, var(--a2ui-border-radius, 8px));
      box-shadow: var(--a2ui-card-box-shadow, 0 2px 4px rgba(0, 0, 0, 0.1));
      background: var(--a2ui-card-background, var(--a2ui-color-surface, #fff));
      color: var(--a2ui-color-on-surface, #333);
      border: var(
        --a2ui-card-border,
        var(--a2ui-border-width, 1px) solid var(--a2ui-color-border, #ccc)
      );
      margin: var(--a2ui-card-margin, var(--a2ui-spacing-m, 16px));
    }
  `;import{html as Ni,nothing as _i,css as Ei}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{classMap as ri}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var z=class extends n{render(){let i=this.controller.props;if(!i)return _i;let e=i.isValid===!1,a={"a2ui-checkbox":!0,"a2ui-invalid":e},r={"a2ui-invalid":e};return Ni`
      <div class="a2ui-checkbox-container">
        <label class=${ri(a)}>
          <input
            type="checkbox"
            class=${ri(r)}
            .checked=${i.value||!1}
            @change=${o=>i.setValue?.(o.target.checked)}
          />
          <span class="a2ui-check-box-text">${i.label}</span>
        </label>
        ${this.renderValidationErrors(i)}
      </div>
    `}};z.tagName="a2ui-checkbox";z.styles=Ei`
    :host,
    a2ui-checkbox {
      display: block;
    }
    .a2ui-checkbox-container {
      display: flex;
      flex-direction: column;
      margin: var(--a2ui-checkbox-margin, var(--a2ui-spacing-m));
    }
    label.a2ui-checkbox {
      display: inline-flex;
      align-items: center;
      gap: var(--a2ui-checkbox-gap, var(--a2ui-spacing-s, 0.5rem));
      font-size: var(
        --a2ui-checkbox-label-font-size,
        var(--a2ui-label-font-size, var(--a2ui-font-size-s))
      );
      font-weight: var(--a2ui-checkbox-label-font-weight, var(--a2ui-label-font-weight, bold));
      cursor: pointer;
    }
    label.a2ui-invalid {
      color: var(--a2ui-checkbox-color-error, red);
    }
    input {
      width: var(--a2ui-checkbox-size, 1rem);
      height: var(--a2ui-checkbox-size, 1rem);
      background: var(--a2ui-checkbox-background, inherit);
      border: var(--a2ui-checkbox-border, var(--a2ui-border));
      border-radius: var(--a2ui-checkbox-border-radius, 4px);
    }
    input.a2ui-invalid {
      outline: 1px solid var(--a2ui-checkbox-color-error, red);
    }
    .a2ui-error-message {
      color: var(--a2ui-checkbox-color-error, red);
      font-size: var(--a2ui-font-size-xs, 0.75rem);
      margin-top: 4px;
    }
  `;import{html as A,nothing as L,css as Mi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{state as Si}from"/vendor/esm/lit@3.3.3/es2022/decorators.mjs";import{classMap as oi}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var Vi=function(t,i,e,a){var r=arguments.length,o=r<3?i:a===null?a=Object.getOwnPropertyDescriptor(i,e):a,s;if(typeof Reflect=="object"&&typeof Reflect.decorate=="function")o=Reflect.decorate(t,i,e,a);else for(var l=t.length-1;l>=0;l--)(s=t[l])&&(o=(r<3?s(o):r>3?s(i,e,o):s(i,e))||o);return r>3&&o&&Object.defineProperty(i,e,o),o},m=class extends n{constructor(){super(...arguments),this.filter=""}render(){let i=this.controller?.props;if(!i)return L;let e=i.value,a=Array.isArray(e)?e:typeof e=="string"?[e]:[],r=i.variant==="multipleSelection",o=i.displayStyle==="chips",s=c=>{let p=i.setValue;typeof p=="function"&&(r?a.includes(c)?p(a.filter(x=>x!==c)):p([...a,c]):p([c]))},l=(i.options||[]).filter(c=>!i.filterable||this.filter===""||String(c.label).toLowerCase().includes(this.filter.toLowerCase())),D=this.context?.dataContext?.surface?.id||"default",U=this.context?.componentModel?.id||"choice-picker",F=(this.context?.dataContext?.path||"/").replace(/[^a-zA-Z0-9-]/g,"_"),Y=`a2ui-choice-${D}-${U}-${F}`;return A`
      ${i.label?A`<label>${i.label}</label>`:L}
      ${i.filterable?A`
            <input
              type="text"
              class="a2ui-filter-input"
              placeholder="Filter options..."
              aria-label="Filter options"
              .value=${this.filter}
              @input=${c=>this.filter=c.target.value}
            />
          `:L}
      <div
        class=${oi({"a2ui-choice-picker":!0,"a2ui-options-group":!o,"a2ui-chips-group":o})}
      >
        ${l.map(c=>o?A`
                <button
                  type="button"
                  class=${oi({"a2ui-chip":!0,"a2ui-chip-selected":a.includes(c.value)})}
                  aria-pressed=${a.includes(c.value)}
                  @click=${()=>s(c.value)}
                >
                  ${c.label}
                </button>
              `:A`
                <label class="a2ui-option-label">
                  <input
                    type=${r?"checkbox":"radio"}
                    name=${r?L:Y}
                    value=${c.value}
                    .checked=${a.includes(c.value)}
                    @change=${()=>s(c.value)}
                    class="a2ui-option-input"
                  />
                  <span class="a2ui-option-text">${c.label}</span>
                </label>
              `)}
      </div>
      ${this.renderValidationErrors(i)}
    `}};m.tagName="a2ui-choicepicker";m.styles=Mi`
    :host,
    .a2ui-choice-picker {
      display: flex;
      flex-direction: column;
      width: 100%;
      gap: var(--a2ui-choicepicker-gap, var(--a2ui-spacing-xs, 0.25rem));
      padding: var(--a2ui-choicepicker-padding, 0);
    }
    .a2ui-options-group {
      display: flex;
      flex-direction: column;
      gap: var(--a2ui-choicepicker-gap, var(--a2ui-spacing-xs, 0.25rem));
    }
    label,
    .a2ui-option-label {
      display: flex;
      align-items: center;
      gap: var(--a2ui-choicepicker-gap, var(--a2ui-spacing-xs, 0.25rem));
      cursor: pointer;
      color: var(--a2ui-text-color-text, var(--a2ui-choicepicker-label-color, inherit));
      font-size: var(--a2ui-choicepicker-label-font-size, inherit);
    }
    :host,
    a2ui-choicepicker > label {
      font-size: var(
        --a2ui-choicepicker-label-font-size,
        var(--a2ui-label-font-size, var(--a2ui-font-size-s))
      );
      font-weight: var(--a2ui-choicepicker-label-font-weight, var(--a2ui-label-font-weight, bold));
    }
    .a2ui-filter-input {
      background-color: var(--a2ui-color-input, #fff);
      color: var(--a2ui-color-on-input, #333);
      border: var(
        --a2ui-textfield-border,
        var(--a2ui-border, 1px solid var(--a2ui-color-border, #ccc))
      );
      border-radius: var(--a2ui-textfield-border-radius, var(--a2ui-spacing-m, 4px));
      padding: var(
        --a2ui-choicepicker-filter-padding,
        var(--a2ui-spacing-xs, 4px) var(--a2ui-spacing-s, 8px)
      );
      margin-bottom: var(--a2ui-choicepicker-filter-margin-bottom, var(--a2ui-spacing-s, 0.25rem));
      font-family: inherit;
    }
    .a2ui-filter-input:focus {
      outline: none;
      border-color: var(--a2ui-textfield-color-border-focus, var(--a2ui-color-primary, #17e));
    }
    .a2ui-option-input {
      width: var(--a2ui-choicepicker-checkbox-size, 1rem);
      height: var(--a2ui-choicepicker-checkbox-size, 1rem);
    }
    .a2ui-chips-group {
      display: flex;
      flex-direction: row;
      flex-wrap: wrap;
      gap: var(--a2ui-choicepicker-gap, var(--a2ui-spacing-xs, 0.25rem));
    }
    .a2ui-chip {
      padding: var(
        --a2ui-choicepicker-chip-padding,
        var(--a2ui-spacing-s, 4px) var(--a2ui-spacing-m, 8px)
      );
      border-radius: var(--a2ui-choicepicker-chip-border-radius, 999px);
      border: var(--a2ui-choicepicker-chip-border, 1px solid var(--a2ui-color-border, #ccc));
      background-color: var(--a2ui-choicepicker-chip-background, var(--a2ui-color-surface, #fff));
      color: var(--a2ui-color-on-surface, inherit);
      cursor: pointer;
      font-size: var(--a2ui-choicepicker-chip-font-size, var(--a2ui-font-size-xs, 0.75rem));
      font-family: inherit;
      font-weight: var(--a2ui-choicepicker-chip-font-weight, normal);
      transition: all 0.2s;
    }
    .a2ui-chip.a2ui-chip-selected {
      background-color: var(
        --a2ui-choicepicker-chip-background-selected,
        var(--a2ui-color-primary, #007bff)
      );
      color: var(--a2ui-color-on-primary, #fff);
      border-color: var(
        --a2ui-choicepicker-chip-background-selected,
        var(--a2ui-color-primary, #007bff)
      );
    }
    .a2ui-error-message {
      color: var(--a2ui-choicepicker-color-error, red);
      font-size: var(--a2ui-font-size-xs, 0.75rem);
    }
  `;Vi([Si()],m.prototype,"filter",void 0);import{html as si,nothing as Ii,css as ji}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{repeat as Li}from"/vendor/esm/lit@3.3.3/es2022/directives/repeat.mjs";var Oi={start:"flex-start",center:"center",end:"flex-end",spaceBetween:"space-between",spaceAround:"space-around",spaceEvenly:"space-evenly",stretch:"stretch"},Ti={start:"flex-start",center:"center",end:"flex-end",stretch:"stretch",baseline:"baseline"};function Bi(t){return typeof t=="object"&&t!==null?`${t.basePath??""}/${t.id}`:String(t)}var C=class extends n{updated(i){super.updated(i);let e=this.controller.props;e&&(e.justify?this.style.justifyContent=Oi[e.justify]??"flex-start":this.style.removeProperty("justify-content"),e.align?this.style.alignItems=Ti[e.align]??"stretch":this.style.removeProperty("align-items"))}render(){let i=this.controller.props;if(!i)return Ii;let e=Array.isArray(i.children)?i.children:[];return si` ${Li(e,Bi,a=>si`${this.renderNode(a)}`)} `}};C.tagName="a2ui-basic-column";C.styles=ji`
    :host,
    a2ui-basic-column {
      display: flex;
      flex-direction: column;
      width: var(--a2ui-column-width, 100%);
      gap: var(--a2ui-column-gap, var(--a2ui-spacing-m));
    }
  `;import{html as O,nothing as d,css as Ri}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";function Di(){let t=new Date,i=t.getFullYear(),e=String(t.getMonth()+1).padStart(2,"0"),a=String(t.getDate()).padStart(2,"0");return`${i}-${e}-${a}`}function h(t,i){if(!t)return"";if(t.includes("T")){let[a,r]=t.split("T");switch(i){case"date":return a?.substring(0,10)??"";case"time":return r?.substring(0,5)??"";case"datetime-local":return`${a?.substring(0,10)??""}T${r?.substring(0,5)??""}`}}return i==="date"?t.includes("-")?t.substring(0,10):"":i==="time"&&t.includes(":")?t.substring(0,5):""}var P=class extends n{render(){let i=this.controller.props;if(!i)return d;let e=i.enableTime??!1,a=i.enableDate??!e,r=typeof i.value=="string"?i.value:i.value?String(i.value):"",o=typeof i.min=="string"?i.min:i.min?String(i.min):"",s=typeof i.max=="string"?i.max:i.max?String(i.max):"",l=h(r,"date"),D=h(r,"time"),U=h(o,"date"),X=h(s,"date"),F=h(o,"time"),Y=h(s,"time"),c=x=>{let y=x.target.value;if(e){let K=r.includes("T")?r.split("T")[1]:r.includes(":")?r:"00:00:00";i.setValue?.(`${y}T${K}`)}else i.setValue?.(y)},p=x=>{let y=x.target.value;if(a){let K=r.includes("T")?r.split("T")[0]:r.includes("-")?r:Di();i.setValue?.(`${K}T${y}:00`)}else i.setValue?.(y)};return O`
      <div class="a2ui-date-time-container">
        ${i.label?O`<label class="a2ui-date-time-label">${i.label}</label>`:d}
        <div class="a2ui-date-time-inputs">
          ${a?O`
                <input
                  type="date"
                  min=${U||d}
                  max=${X||d}
                  .value=${l}
                  @change=${c}
                  class="a2ui-date-time-input"
                />
              `:d}
          ${e?O`
                <input
                  type="time"
                  min=${F||d}
                  max=${Y||d}
                  .value=${D}
                  @change=${p}
                  class="a2ui-date-time-input"
                />
              `:d}
        </div>
        ${this.renderValidationErrors(i)}
      </div>
    `}};P.tagName="a2ui-datetimeinput";P.styles=Ri`
    .a2ui-date-time-container {
      display: flex;
      flex-direction: column;
      gap: var(--a2ui-spacing-xs, 4px);
      width: var(--a2ui-datetimeinput-width, 100%);
    }
    input {
      box-sizing: border-box;
      width: 100%;
    }
    .a2ui-date-time-label {
      font-size: var(
        --a2ui-datetimeinput-label-font-size,
        var(--a2ui-label-font-size, var(--a2ui-font-size-s, 14px))
      );
      font-weight: var(--a2ui-datetimeinput-label-font-weight, bold);
      color: var(--a2ui-text-color-text, var(--a2ui-color-on-background, #333));
    }
    .a2ui-date-time-inputs {
      display: flex;
      gap: var(--a2ui-spacing-s, 8px);
      width: 100%;
    }
    .a2ui-date-time-input {
      padding: var(--a2ui-datetimeinput-padding, 8px);
      border-radius: var(--a2ui-datetimeinput-border-radius, 4px);
      border: var(--a2ui-datetimeinput-border, 1px solid var(--a2ui-color-border, #ccc));
      background-color: var(--a2ui-datetimeinput-background, var(--a2ui-color-input, #fff));
      color: var(--a2ui-datetimeinput-color, var(--a2ui-color-on-input, #333));
      font-family: inherit;
      flex: 1;
    }
    .a2ui-date-time-input::-webkit-datetime-edit,
    .a2ui-date-time-input::-webkit-datetime-edit-fields-wrapper {
      color: var(--a2ui-datetimeinput-color, var(--a2ui-color-on-input, #333));
    }
    .a2ui-error-message {
      color: var(--a2ui-datetimeinput-color-error, red);
      font-size: var(--a2ui-font-size-xs, 0.75rem);
    }
  `;import{html as Ui,nothing as Fi,css as Yi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{classMap as Ki}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var N=class extends n{render(){let i=this.controller.props;if(!i)return Fi;let a={"a2ui-divider":!0,["a2ui-divider-"+(i.axis??"horizontal")]:!0};return Ui`<hr class=${Ki(a)} />`}};N.tagName="a2ui-divider";N.styles=Yi`
    .a2ui-divider {
      border: 0;
      border-top: var(
        --a2ui-divider-border,
        var(--a2ui-border-width, 1px) solid var(--a2ui-color-border, #ccc)
      );
      margin: var(--a2ui-divider-spacing, var(--a2ui-spacing-m, 16px)) 0;
      width: 100%;
    }
    .a2ui-divider.a2ui-divider-vertical {
      width: var(--a2ui-border-width, 1px);
      height: 100%;
      margin: 0 var(--a2ui-divider-spacing, var(--a2ui-spacing-m, 16px));
      border-top: 0;
      border-left: var(
        --a2ui-divider-border,
        var(--a2ui-border-width, 1px) solid var(--a2ui-color-border, #ccc)
      );
    }
  `;import{html as ni,nothing as Gi,css as Ji}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";var li={play:"play_arrow",rewind:"fast_rewind",favoriteOff:"favorite_border",starOff:"star_border"};function Zi(t){return li[t]?li[t]:t.replace(/[A-Z]/g,i=>`_${i.toLowerCase()}`)}var _=class extends n{render(){let i=this.controller.props;if(!i)return Gi;let e=i.name;if(typeof e=="object"&&e!==null&&"svgPath"in e){let o=e.svgPath;return ni`
        <svg class="a2ui-icon a2ui-icon-svg" viewBox="0 0 24 24">
          <path d=${o}></path>
        </svg>
      `}let r=typeof e=="string"?Zi(e):"";return ni`<i class="material-icons a2ui-icon">${r}</i>`}};_.tagName="a2ui-icon";_.styles=Ji`
    .a2ui-icon {
      display: inline-block;
      width: var(--a2ui-icon-size, 24px);
      height: var(--a2ui-icon-size, 24px);
      font-size: var(--a2ui-icon-size, 24px);
      font-style: normal;
      font-weight: normal;
      font-family: var(--a2ui-icon-font-family, 'Material Icons', 'Material Symbols Outlined');
      color: var(
        --a2ui-icon-color,
        var(--a2ui-text-color-text, var(--a2ui-color-on-background, #333))
      );
      font-variation-settings: var(--a2ui-icon-font-variation-settings, 'FILL' 1);
      line-height: 1;
      text-transform: none;
      letter-spacing: normal;
      word-wrap: normal;
      white-space: nowrap;
      direction: ltr;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      -moz-osx-font-smoothing: grayscale;
      font-feature-settings: 'liga';
      vertical-align: middle;
    }
    .a2ui-icon.a2ui-icon-svg {
      fill: currentColor;
    }
  `;import{html as qi,nothing as ci,css as Wi}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{styleMap as Hi}from"/vendor/esm/lit@3.3.3/es2022/directives/style-map.mjs";import{sanitizeMediaUrl as Qi}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/common/sanitize_media_url.mjs";var Xi={contain:"contain",cover:"cover",fill:"fill",none:"none",scaleDown:"scale-down"},E=class extends n{render(){let i=this.controller.props;if(!i)return ci;let e=i.variant||"default",a=i.fit||"cover",r=Xi[a]??a,o=Qi(i.url);return qi`<img
      src=${o??ci}
      alt=${i.description||""}
      style=${Hi({objectFit:r})}
      class="a2ui-image a2ui-image-${e}"
    />`}};E.tagName="a2ui-image";E.styles=Wi`
    .a2ui-image {
      display: block;
      max-width: 100%;
      height: auto;
      border-radius: var(--a2ui-image-border-radius, 0);
    }
    .a2ui-image.a2ui-image-icon {
      width: var(--a2ui-image-icon-size, 24px);
      height: var(--a2ui-image-icon-size, 24px);
    }
    .a2ui-image.a2ui-image-avatar {
      width: var(--a2ui-image-avatar-size, 40px);
      height: var(--a2ui-image-avatar-size, 40px);
      border-radius: 50%;
    }
    .a2ui-image.a2ui-image-smallFeature {
      max-width: var(--a2ui-image-small-feature-size, 100px);
    }
    .a2ui-image.a2ui-image-largeFeature {
      max-height: var(--a2ui-image-large-feature-size, 400px);
    }
    .a2ui-image.a2ui-image-header {
      height: var(--a2ui-image-header-size, 200px);
    }
  `;import{html as f,nothing as ui,css as ie}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{repeat as Z}from"/vendor/esm/lit@3.3.3/es2022/directives/repeat.mjs";import{styleMap as ee}from"/vendor/esm/lit@3.3.3/es2022/directives/style-map.mjs";var ae={start:"flex-start",center:"center",end:"flex-end",stretch:"stretch",baseline:"baseline"};function q(t){return typeof t=="object"&&t!==null?`${t.basePath??""}/${t.id}`:String(t)}var V=class extends n{render(){let i=this.controller.props;if(!i)return ui;let e=Array.isArray(i.children)?i.children:[],a=i.listStyle,r=i.direction||"vertical",o=i.align?ae[i.align]??"stretch":void 0,s=o?ee({alignItems:o}):ui;return a==="ordered"?f`
        <ol class="a2ui-list a2ui-list-${r}" style=${s}>
          ${Z(e,q,l=>f`<li>${this.renderNode(l)}</li>`)}
        </ol>
      `:a==="unordered"?f`
        <ul class="a2ui-list a2ui-list-${r}" style=${s}>
          ${Z(e,q,l=>f`<li>${this.renderNode(l)}</li>`)}
        </ul>
      `:f`
      <div class="a2ui-list a2ui-list-${r}" style=${s}>
        ${Z(e,q,l=>f`<div class="a2ui-list-item-none">${this.renderNode(l)}</div>`)}
      </div>
    `}};V.tagName="a2ui-list";V.styles=ie`
    .a2ui-list {
      display: flex;
      padding-inline-start: var(--a2ui-list-padding, var(--a2ui-spacing-l, 24px));
      margin: 0;
    }
    .a2ui-list.a2ui-list-vertical {
      flex-direction: column;
      gap: var(--a2ui-list-gap, var(--a2ui-spacing-s, 8px));
    }
    .a2ui-list.a2ui-list-horizontal {
      flex-direction: row;
      gap: var(--a2ui-list-gap, var(--a2ui-spacing-m, 16px));
      list-style-position: inside;
    }
    .a2ui-list-item-none {
      display: block;
    }
    .a2ui-list-horizontal .a2ui-list-item-none {
      display: inline-block;
    }
  `;import{html as T,nothing as B,css as re}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{state as oe}from"/vendor/esm/lit@3.3.3/es2022/decorators.mjs";var te=function(t,i,e,a){var r=arguments.length,o=r<3?i:a===null?a=Object.getOwnPropertyDescriptor(i,e):a,s;if(typeof Reflect=="object"&&typeof Reflect.decorate=="function")o=Reflect.decorate(t,i,e,a);else for(var l=t.length-1;l>=0;l--)(s=t[l])&&(o=(r<3?s(o):r>3?s(i,e,o):s(i,e))||o);return r>3&&o&&Object.defineProperty(i,e,o),o},v=class extends n{constructor(){super(...arguments),this.isOpen=!1}openModal(){this.isOpen=!0}closeModal(){this.isOpen=!1}render(){let i=this.controller.props;return i?T`
      <div class="a2ui-modal-wrapper">
        <div @click=${()=>this.openModal()} class="a2ui-modal-trigger">
          ${i.trigger?T`${this.renderNode(i.trigger)}`:B}
        </div>
        ${this.isOpen?T`
              <div class="a2ui-modal-overlay" @click=${()=>this.closeModal()}>
                <div
                  class="a2ui-modal-content"
                  role="dialog"
                  aria-modal="true"
                  @click=${e=>e.stopPropagation()}
                >
                  <button
                    type="button"
                    class="a2ui-modal-close"
                    aria-label="Close"
                    @click=${()=>this.closeModal()}
                  >
                    &times;
                  </button>
                  ${i.content?T`${this.renderNode(i.content)}`:B}
                </div>
              </div>
            `:B}
      </div>
    `:B}};v.tagName="a2ui-modal";v.styles=re`
    :host,
    a2ui-modal {
      display: inline-block;
    }
    .a2ui-modal-wrapper {
      display: inline-block;
    }
    .a2ui-modal-trigger {
      cursor: pointer;
    }
    .a2ui-modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: var(--a2ui-modal-backdrop-bg, rgba(0, 0, 0, 0.5));
      display: flex;
      justify-content: center;
      align-items: center;
      z-index: 1000;
    }
    .a2ui-modal-content {
      background: var(--a2ui-modal-background, var(--a2ui-color-surface, #fff));
      padding: var(--a2ui-modal-padding, var(--a2ui-spacing-xl, 32px));
      border-radius: var(--a2ui-modal-border-radius, var(--a2ui-border-radius, 8px));
      position: relative;
      min-width: 300px;
      max-width: 80%;
      max-height: 80%;
      overflow-y: auto;
      box-shadow: var(--a2ui-modal-box-shadow, 0 10px 25px rgba(0, 0, 0, 0.2));
    }
    .a2ui-modal-close {
      position: absolute;
      top: 10px;
      right: 15px;
      border: none;
      background: none;
      font-size: 24px;
      cursor: pointer;
      color: var(--a2ui-text-caption-color, #999);
    }
    .a2ui-modal-close:hover {
      color: var(--a2ui-text-color, #333);
    }
  `;te([oe()],v.prototype,"isOpen",void 0);import{html as di,nothing as se,css as ne}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{repeat as le}from"/vendor/esm/lit@3.3.3/es2022/directives/repeat.mjs";var ce={start:"flex-start",center:"center",end:"flex-end",spaceBetween:"space-between",spaceAround:"space-around",spaceEvenly:"space-evenly",stretch:"stretch"},ue={start:"flex-start",center:"center",end:"flex-end",stretch:"stretch",baseline:"baseline"};function de(t){return typeof t=="object"&&t!==null?`${t.basePath??""}/${t.id}`:String(t)}var M=class extends n{updated(i){super.updated(i);let e=this.controller.props;e&&(e.justify?this.style.justifyContent=ce[e.justify]??"flex-start":this.style.removeProperty("justify-content"),e.align?this.style.alignItems=ue[e.align]??"stretch":this.style.removeProperty("align-items"))}render(){let i=this.controller.props;if(!i)return se;let e=Array.isArray(i.children)?i.children:[];return di` ${le(e,de,a=>di`${this.renderNode(a)}`)} `}};M.tagName="a2ui-basic-row";M.styles=ne`
    :host,
    a2ui-basic-row {
      display: flex;
      flex-direction: row;
      gap: var(--a2ui-row-gap, var(--a2ui-spacing-m));
    }
  `;import{html as pe,nothing as pi,css as me}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";var S=class extends n{render(){let i=this.controller.props;if(!i)return pi;let e=i.min??0,a=i.max??100,r="steps"in i?i.steps:void 0,o=typeof r=="number"&&r>0&&a>e?(a-e)/r:pi;return pe`
      <div class="a2ui-slider-container">
        <div class="a2ui-slider-header">
          <span class="a2ui-slider-label">${i.label}</span>
          <span class="a2ui-slider-value">${i.value}</span>
        </div>
        <input
          type="range"
          min=${e}
          max=${a}
          step=${o}
          .value=${i.value?.toString()||"0"}
          @input=${s=>i.setValue?.(Number(s.target.value))}
          class="a2ui-slider"
        />
        ${this.renderValidationErrors(i)}
      </div>
    `}};S.tagName="a2ui-slider";S.styles=me`
    .a2ui-slider-container {
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: var(--a2ui-spacing-xs, 4px);
      margin: var(--a2ui-slider-margin, var(--a2ui-spacing-m, 16px));
    }
    .a2ui-slider-header {
      display: flex;
      justify-content: space-between;
      font-size: var(
        --a2ui-slider-label-font-size,
        var(--a2ui-label-font-size, var(--a2ui-font-size-s, 14px))
      );
      font-weight: var(--a2ui-slider-label-font-weight, bold);
      color: var(--a2ui-text-color-text, var(--a2ui-color-on-background, #333));
    }
    .a2ui-slider {
      width: 100%;
      cursor: pointer;
      accent-color: var(--a2ui-slider-thumb-color, var(--a2ui-color-primary, #007bff));
      background: var(--a2ui-slider-track-color, var(--a2ui-color-secondary, #e9ecef));
    }
    .a2ui-error-message {
      color: var(--a2ui-slider-color-error, red);
      font-size: var(--a2ui-font-size-xs, 0.75rem);
    }
  `;import{html as W,nothing as mi,css as fe}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{state as ve}from"/vendor/esm/lit@3.3.3/es2022/decorators.mjs";import{classMap as be}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var he=function(t,i,e,a){var r=arguments.length,o=r<3?i:a===null?a=Object.getOwnPropertyDescriptor(i,e):a,s;if(typeof Reflect=="object"&&typeof Reflect.decorate=="function")o=Reflect.decorate(t,i,e,a);else for(var l=t.length-1;l>=0;l--)(s=t[l])&&(o=(r<3?s(o):r>3?s(i,e,o):s(i,e))||o);return r>3&&o&&Object.defineProperty(i,e,o),o},b=class extends n{constructor(){super(...arguments),this.activeIndex=0}willUpdate(i){super.willUpdate(i);let e=this.controller?.props;e?.tabs&&this.activeIndex>=e.tabs.length&&(this.activeIndex=0)}render(){let i=this.controller?.props;return!i||!i.tabs?mi:W`
      <div class="a2ui-tabs">
        <div class="a2ui-tab-bar">
          ${i.tabs?.map((e,a)=>W`
              <button
                class=${be({"a2ui-tab-button":!0,"a2ui-tab-button-active":a===this.activeIndex})}
                @click=${()=>this.activeIndex=a}
              >
                ${e.title}
              </button>
            `)}
        </div>
        <div class="a2ui-tab-content">
          ${i.tabs[this.activeIndex]?W`${this.renderNode(i.tabs[this.activeIndex].child)}`:mi}
        </div>
      </div>
    `}};b.tagName="a2ui-tabs";b.styles=fe`
    .a2ui-tabs {
      display: flex;
      flex-direction: column;
      width: 100%;
    }
    .a2ui-tab-bar {
      display: flex;
      border-bottom: var(--a2ui-tabs-border, 2px solid var(--a2ui-color-border, #eee));
      gap: var(--a2ui-spacing-m, 16px);
    }
    .a2ui-tab-button {
      padding: var(--a2ui-spacing-s, 8px) var(--a2ui-spacing-m, 16px);
      border: none;
      background: var(--a2ui-tabs-header-background, transparent);
      cursor: pointer;
      font-weight: 500;
      color: var(--a2ui-tabs-header-color, var(--a2ui-text-caption-color, #666));
      border-bottom: 2px solid transparent;
      margin-bottom: -2px;
    }
    .a2ui-tab-button.a2ui-tab-button-active {
      background: var(--a2ui-tabs-header-background-active, transparent);
      color: var(--a2ui-tabs-header-color-active, var(--a2ui-color-primary, #007bff));
      border-bottom: 2px solid var(--a2ui-color-primary, #007bff);
    }
    .a2ui-tab-content {
      padding: var(--a2ui-tabs-content-padding, var(--a2ui-spacing-m, 16px) 0);
    }
  `;he([ve()],b.prototype,"activeIndex",void 0);import{html as u,nothing as hi,css as xe}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{consume as ye}from"/vendor/esm/@lit/context@_1.1.6__784fb81524.js";import{Context as $e}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/context/context.mjs";import{markdown as we}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/universal/basic_catalog/directives/directives.mjs";var ge=function(t,i,e,a){var r=arguments.length,o=r<3?i:a===null?a=Object.getOwnPropertyDescriptor(i,e):a,s;if(typeof Reflect=="object"&&typeof Reflect.decorate=="function")o=Reflect.decorate(t,i,e,a);else for(var l=t.length-1;l>=0;l--)(s=t[l])&&(o=(r<3?s(o):r>3?s(i,e,o):s(i,e))||o);return r>3&&o&&Object.defineProperty(i,e,o),o},ke=new Set(["h1","h2","h3","h4","h5","caption"]),g=class extends n{render(){let i=this.controller.props;if(!i)return hi;let e=i.variant||"body",a=typeof i.text=="string"?i.text:String(i.text??""),r=typeof i.weight=="number"?`flex: ${i.weight};`:hi;if(ke.has(e)){let s=u`${a}`;switch(e){case"h1":s=u`<h1>${a}</h1>`;break;case"h2":s=u`<h2>${a}</h2>`;break;case"h3":s=u`<h3>${a}</h3>`;break;case"h4":s=u`<h4>${a}</h4>`;break;case"h5":s=u`<h5>${a}</h5>`;break;case"caption":s=u`<em>${a}</em>`;break}return u`<span class="a2ui-text a2ui-text-${e}" style=${r}
        >${s}</span
      >`}let o=we(a,this.markdownRenderer);return u`<span class="a2ui-text a2ui-text-${e}" style=${r}
      >${o}</span
    >`}};g.tagName="a2ui-basic-text";g.styles=xe`
    :host {
      display: contents;
    }
    .a2ui-text p,
    .a2ui-text h1,
    .a2ui-text h2,
    .a2ui-text h3,
    .a2ui-text h4,
    .a2ui-text h5,
    .a2ui-text h6,
    .a2ui-text ol,
    .a2ui-text ul,
    .a2ui-text li,
    .a2ui-text blockquote,
    .a2ui-text pre {
      margin: var(--_a2ui-text-margin, 0);
    }
    .a2ui-text {
      color: var(--_a2ui-text-color, var(--a2ui-text-color-text, var(--a2ui-color-on-background)));
    }
    .a2ui-text h1,
    .a2ui-text h2,
    .a2ui-text h3,
    .a2ui-text h4,
    .a2ui-text h5,
    .a2ui-text h6 {
      font-family: var(--a2ui-font-family-title, inherit);
      line-height: var(--a2ui-line-height-headings, 1.2);
    }
    .a2ui-text h1 {
      font-size: var(--a2ui-font-size-2xl);
    }
    .a2ui-text h2 {
      font-size: var(--a2ui-font-size-xl);
    }
    .a2ui-text h3 {
      font-size: var(--a2ui-font-size-l);
    }
    .a2ui-text p,
    .a2ui-text h4 {
      font-size: var(--a2ui-font-size-m);
    }
    .a2ui-text h5 {
      font-size: var(--a2ui-font-size-s);
    }
    .a2ui-text p {
      line-height: var(--a2ui-line-height-body, 1.5);
    }
    .a2ui-text.a2ui-text-caption {
      font-size: var(--a2ui-font-size-xs);
      color: var(--a2ui-text-caption-color, light-dark(#666, #aaa));
    }
    .a2ui-text a {
      color: var(--a2ui-text-a-color, inherit);
      font-weight: var(--a2ui-text-a-font-weight, inherit);
    }
  `;ge([ye({context:$e.markdown,subscribe:!0})],g.prototype,"markdownRenderer",void 0);import{html as R,nothing as H,css as ze}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{classMap as fi}from"/vendor/esm/lit@3.3.3/es2022/directives/class-map.mjs";var I=class extends n{render(){let i=this.controller.props;if(!i)return H;let e=i.isValid===!1,a=l=>i.setValue?.(l.target.value),r="text";i.variant==="number"&&(r="number"),i.variant==="obscured"&&(r="password");let o={"a2ui-textfield":!0,"a2ui-invalid":e},s="placeholder"in i&&i.placeholder||H;return R`
      ${i.label?R`<label>${i.label}</label>`:H}
      ${i.variant==="longText"?R`<textarea
            class=${fi(o)}
            placeholder=${s}
            .value=${i.value||""}
            @input=${a}
          ></textarea>`:R`<input
            type=${r}
            class=${fi(o)}
            placeholder=${s}
            .value=${i.value||""}
            @input=${a}
          />`}
      ${this.renderValidationErrors(i)}
    `}};I.tagName="a2ui-basic-textfield";I.styles=ze`
    :host,
    a2ui-basic-textfield {
      display: flex;
      flex-direction: column;
      width: var(--a2ui-textfield-width, 100%);
      gap: var(--a2ui-spacing-xs, 0.25rem);
    }
    .a2ui-textfield {
      box-sizing: border-box;
      width: 100%;
      background-color: var(--a2ui-color-input, #fff);
      color: var(--a2ui-color-on-input, #333);
      border: var(--a2ui-textfield-border, var(--a2ui-border));
      border-radius: var(--a2ui-textfield-border-radius, var(--a2ui-spacing-m));
      padding: var(--a2ui-textfield-padding, var(--a2ui-spacing-m));
      font-family: inherit;
    }
    .a2ui-textfield:focus {
      outline: none;
      border-color: var(--a2ui-textfield-color-border-focus, var(--a2ui-color-primary, #17e));
    }
    .a2ui-textfield.a2ui-invalid {
      border-color: var(--a2ui-textfield-color-error, red);
    }
    label {
      font-size: var(
        --a2ui-textfield-label-font-size,
        var(--a2ui-label-font-size, var(--a2ui-font-size-s))
      );
      font-weight: var(--a2ui-textfield-label-font-weight, var(--a2ui-label-font-weight, bold));
    }
    .a2ui-error-message {
      color: var(--a2ui-textfield-color-error, red);
      font-size: var(--a2ui-font-size-xs, 0.75rem);
    }
  `;import{html as Ae,nothing as Q,css as Ce}from"/vendor/esm/lit@3.3.3/es2022/lit.mjs";import{sanitizeMediaUrl as vi}from"/vendor/esm/@a2ui/web_core@0.15.0/X-ZGxpdEAzLjMuMw/es2022/src/common/sanitize_media_url.mjs";var j=class extends n{render(){let i=this.controller.props;if(!i)return Q;let e=vi(i.url),a="posterUrl"in i?vi(i.posterUrl):void 0;return Ae`
      <div class="a2ui-video-container">
        <video
          src=${e??Q}
          poster=${a??Q}
          controls
          class="a2ui-video"
        >
          Your browser does not support the video tag.
        </video>
      </div>
    `}};j.tagName="a2ui-video";j.styles=Ce`
    .a2ui-video-container {
      width: 100%;
      max-width: 100%;
    }
    .a2ui-video {
      width: 100%;
      height: auto;
      display: block;
      border-radius: var(--a2ui-video-border-radius, 0);
    }
  `;export{$ as A2uiAudioPlayerElement,w as A2uiBasicButtonElement,C as A2uiBasicColumnElement,M as A2uiBasicRowElement,g as A2uiBasicTextElement,I as A2uiBasicTextFieldElement,k as A2uiCardElement,z as A2uiCheckBoxElement,m as A2uiChoicePickerElement,P as A2uiDateTimeInputElement,N as A2uiDividerElement,_ as A2uiIconElement,E as A2uiImageElement,V as A2uiListElement,v as A2uiModalElement,S as A2uiSliderElement,b as A2uiTabsElement,j as A2uiVideoElement,n as BasicCatalogA2uiLitElement};
//# sourceMappingURL=index.mjs.map