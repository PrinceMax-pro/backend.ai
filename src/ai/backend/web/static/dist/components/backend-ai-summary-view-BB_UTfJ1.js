import{_ as t,n as e,t as i,h as s,I as a,a as r,i as o,k as n,g as l,e as p,B as c,b as u,c as d,d as h,f as m,j as g,s as _,l as v}from"./backend-ai-webui-CYa1T8s6.js";import"./backend-ai-session-launcher-BS_ZWH1z.js";import"./lablup-activity-panel-DqYslxGX.js";import"./lablup-progress-bar-DYTXuADk.js";import"./mwc-switch-ffP68jDO.js";import"./mwc-check-list-item-wh-PTqO8.js";let b=class extends s{constructor(){super(...arguments),this.currentNumber=50,this.maxNumber=100,this.unit="%",this.url="",this.textcolor="#888888",this.chartcolor="#ff2222",this.size=200,this.fontsize=60,this.chartFontSize="0",this.indicatorPath="",this.prefix="",this.sizeParam=""}static get is(){return"lablup-piechart"}static get styles(){return[a,r,o`
        #chart {
          cursor: pointer;
        }
      `]}firstUpdated(){var t,e,i,s,a,r,o;this.sizeParam=this.size+"px";let n=this.fontsize/this.size;n=n>=.5?.3:.9/this.currentNumber.toString().length,this.chartFontSize=n.toString();let l=null===(t=this.shadowRoot)||void 0===t?void 0:t.querySelector("#chart"),p=null===(e=this.shadowRoot)||void 0===e?void 0:e.querySelector("#chart-text"),c=null===(i=this.shadowRoot)||void 0===i?void 0:i.querySelector("#unit-text"),u=(.3-.05*this.unit.length).toString();l.setAttribute("fill",this.chartcolor),p.setAttribute("fill",this.textcolor),p.setAttribute("font-size",this.chartFontSize),c.setAttribute("font-size",u),l.setAttribute("width",this.sizeParam),l.setAttribute("height",this.sizeParam),this.indicatorPath="M 0.5 0.5 L0.5 0 ";var d=100*(this.maxNumber-this.currentNumber)/this.maxNumber;d>12.5&&(this.indicatorPath=this.indicatorPath+"L1 0 "),d>37.5&&(this.indicatorPath=this.indicatorPath+"L1 1 "),d>62.5&&(this.indicatorPath=this.indicatorPath+"L0 1 "),d>87.5&&(this.indicatorPath=this.indicatorPath+"L0 0 ");let h=d/100*2*Math.PI,m=Math.sin(h)/Math.cos(h),g=0,_=0;d<=12.5||d>87.5?(_=.5,g=_*m):d>12.5&&d<=37.5?(g=.5,_=g/m):d>37.5&&d<=62.5?(_=-.5,g=_*m):d>62.5&&d<=87.5&&(g=-.5,_=g/m),g+=.5,_=.5-_,this.indicatorPath=this.indicatorPath+"L"+g+" "+_+" z",null===(a=null===(s=this.shadowRoot)||void 0===s?void 0:s.querySelector("#pievalue"))||void 0===a||a.setAttribute("d",this.indicatorPath),void 0!==this.url&&""!==this.url&&(null===(o=null===(r=this.shadowRoot)||void 0===r?void 0:r.querySelector("#chart"))||void 0===o||o.addEventListener("tap",this._moveTo.bind(this))),this.requestUpdate()}connectedCallback(){super.connectedCallback()}_moveTo(){window.location.href=this.url}render(){return n`
      <svg
        id="chart"
        xmlns="http://www.w3.org/2000/svg"
        xmlns:xlink="http://www.w3.org/1999/xlink"
        version="1.1"
        viewBox="0 0 1 1"
        style="background-color:transparent;"
      >
        <g id="piechart">
          <circle cx="0.5" cy="0.5" r="0.5" />
          <circle cx="0.5" cy="0.5" r="0.40" fill="rgba(255,255,255,0.9)" />
          <path id="pievalue" stroke="none" fill="rgba(255, 255, 255, 0.75)" />
          <text
            id="chart-text"
            x="0.5"
            y="0.5"
            font-family="Roboto"
            text-anchor="middle"
            dy="0.1"
          >
            <tspan>${this.prefix}</tspan>
            <tspan>${this.currentNumber}</tspan>
            <tspan id="unit-text" font-size="0.2" dy="-0.07">
              ${this.unit}
            </tspan>
          </text>
        </g>
      </svg>
    `}};t([e({type:Number})],b.prototype,"currentNumber",void 0),t([e({type:Number})],b.prototype,"maxNumber",void 0),t([e({type:String})],b.prototype,"unit",void 0),t([e({type:String})],b.prototype,"url",void 0),t([e({type:String})],b.prototype,"textcolor",void 0),t([e({type:String})],b.prototype,"chartcolor",void 0),t([e({type:Number})],b.prototype,"size",void 0),t([e({type:Number})],b.prototype,"fontsize",void 0),t([e({type:String})],b.prototype,"chartFontSize",void 0),t([e({type:String})],b.prototype,"indicatorPath",void 0),t([e({type:String})],b.prototype,"prefix",void 0),t([e({type:String})],b.prototype,"sizeParam",void 0),b=t([i("lablup-piechart")],b);let y=class extends s{constructor(){super(...arguments),this.releaseURL="https://raw.githubusercontent.com/lablup/backend.ai-webui/release/version.json",this.localVersion="",this.localBuild="",this.remoteVersion="",this.remoteBuild="",this.remoteRevision="",this.updateChecked=!1,this.updateNeeded=!1,this.updateURL=""}static get styles(){return[]}render(){return n``}firstUpdated(){this.notification=globalThis.lablupNotification,globalThis.isElectron&&void 0!==globalThis.backendaioptions&&globalThis.backendaioptions.get("automatic_update_check",!0)&&this.checkRelease()}async checkRelease(){this.updateChecked||fetch(this.releaseURL).then((t=>t.json())).then((t=>{this.updateChecked=!0,this.remoteVersion=t.package,this.remoteBuild=t.build,this.remoteRevision=t.revision,this.compareVersion(globalThis.packageVersion,this.remoteVersion)<0&&(this.updateNeeded=!0,this.updateURL=`https://github.com/lablup/backend.ai-webui/releases/tag/v${this.remoteVersion}`,globalThis.isElectron&&(this.notification.text=l("update.NewWebUIVersionAvailable")+" "+this.remoteVersion,this.notification.detail=l("update.NewWebUIVersionAvailable"),this.notification.url=this.updateURL,this.notification.show()))})).catch((t=>{const e=globalThis.backendaioptions.get("automatic_update_count_trial",0);e>3&&globalThis.backendaioptions.set("automatic_update_check",!1),globalThis.backendaioptions.set("automatic_update_count_trial",e+1)}))}compareVersion(t,e){if("string"!=typeof t)return 0;if("string"!=typeof e)return 0;t=t.split("."),e=e.split(".");const i=Math.min(t.length,e.length);for(let s=0;s<i;++s){if(t[s]=parseInt(t[s],10),e[s]=parseInt(e[s],10),t[s]>e[s])return 1;if(t[s]<e[s])return-1}return t.length==e.length?0:t.length<e.length?-1:1}};t([e({type:String})],y.prototype,"releaseURL",void 0),t([e({type:String})],y.prototype,"localVersion",void 0),t([e({type:String})],y.prototype,"localBuild",void 0),t([e({type:String})],y.prototype,"remoteVersion",void 0),t([e({type:String})],y.prototype,"remoteBuild",void 0),t([e({type:String})],y.prototype,"remoteRevision",void 0),t([e({type:Boolean})],y.prototype,"updateChecked",void 0),t([e({type:Boolean})],y.prototype,"updateNeeded",void 0),t([e({type:String})],y.prototype,"updateURL",void 0),t([e({type:Object})],y.prototype,"notification",void 0),y=t([i("backend-ai-release-check")],y);let f=class extends s{constructor(){super(...arguments),this.active=!1}static get styles(){return[o`
        mwc-circular-progress {
          width: 48px;
          height: 48px;
          position: fixed;
          --mdc-theme-primary: #e91e63;
          top: calc(50vh - 24px);
        }
      `]}render(){return n`
      <link rel="stylesheet" href="resources/custom.css" />
      <mwc-circular-progress id="spinner" indeterminate></mwc-circular-progress>
    `}shouldUpdate(){return this.active}firstUpdated(){var t;this.spinner=null===(t=this.shadowRoot)||void 0===t?void 0:t.querySelector("#spinner"),this.active=!0}connectedCallback(){super.connectedCallback()}disconnectedCallback(){super.disconnectedCallback()}async show(){this.active=!0,await this.updateComplete,this.spinner.style.display="block"}async hide(){this.active=!0,await this.updateComplete,this.spinner.style.display="none",this.active=!1}async toggle(){await this.updateComplete,!0===this.spinner.active?(this.active=!0,this.spinner.style.display="none",this.active=!1):(this.active=!0,this.spinner.style.display="block")}};t([e({type:Object})],f.prototype,"spinner",void 0),t([e({type:Boolean,reflect:!0})],f.prototype,"active",void 0),f=t([i("lablup-loading-spinner")],f);let x=class extends c{constructor(){super(...arguments),this.condition="running",this.sessions=0,this.agents=0,this.is_admin=!1,this.is_superadmin=!1,this.resources=Object(),this.authenticated=!1,this.manager_version="",this.webui_version="",this.cpu_total=0,this.cpu_used=0,this.cpu_percent="0",this.cpu_total_percent="0",this.cpu_total_usage_ratio=0,this.cpu_current_usage_ratio=0,this.mem_total="0",this.mem_used="0",this.mem_allocated="0",this.mem_total_usage_ratio=0,this.mem_current_usage_ratio=0,this.mem_current_usage_percent="0",this.cuda_gpu_total=0,this.cuda_gpu_used=0,this.cuda_fgpu_total=0,this.cuda_fgpu_used=0,this.rocm_gpu_total=0,this.rocm_gpu_used=0,this.tpu_total=0,this.tpu_used=0,this.ipu_total=0,this.ipu_used=0,this.atom_total=0,this.atom_used=0,this.atom_plus_total=0,this.atom_plus_used=0,this.gaudi2_total=0,this.gaudi2_used=0,this.warboy_total=0,this.warboy_used=0,this.rngd_total=0,this.rngd_used=0,this.hyperaccel_lpu_total=0,this.hyperaccel_lpu_used=0,this.notification=Object(),this.announcement="",this.height=0}static get styles(){return[u,a,r,d,o`
        ul {
          padding-left: 0;
        }

        ul li {
          list-style: none;
          font-size: 14px;
        }

        li:before {
          padding: 3px;
          transform: rotate(-45deg) translateY(-2px);
          transition: color ease-in 0.2s;
          border: solid;
          border-width: 0 2px 2px 0;
          border-color: #242424;
          margin-right: 10px;
          content: '';
          display: inline-block;
        }

        span.indicator {
          width: 100px;
        }

        div.card {
          margin: 20px;
        }

        div.big.indicator {
          font-size: 48px;
        }

        a,
        a:visited {
          color: #222222;
        }

        a:hover {
          color: var(--token-colorPrimary, #3e872d);
        }

        mwc-linear-progress {
          width: 260px;
          height: 15px;
          border-radius: 0;
          --mdc-theme-primary: #3677eb;
        }

        mwc-linear-progress.start-bar {
          border-top-left-radius: 3px;
          border-top-right-radius: 3px;
          --mdc-theme-primary: #3677eb;
        }

        mwc-linear-progress.end-bar {
          border-bottom-left-radius: 3px;
          border-bottom-right-radius: 3px;
          --mdc-theme-primary: #98be5a;
        }

        mwc-icon-button.update-button {
          --mdc-icon-size: 16px;
          --mdc-icon-button-size: 24px;
          color: red;
        }

        mwc-icon.update-icon {
          --mdc-icon-size: 16px;
          --mdc-icon-button-size: 24px;
          color: black;
        }

        img.resource-type-icon {
          width: 16px;
          height: 16px;
          margin-right: 5px;
        }

        div.indicators {
          min-height: 83px;
          padding: 10px 20px;
          background-color: var(--token-colorBgContainer, #f6f6f6);
        }

        .system-health-indicator {
          width: 90px;
        }

        .resource {
          margin-bottom: 10px;
          margin-left: 5px;
        }

        .resource-line {
          margin-left: 85px;
        }
      `]}firstUpdated(){this.notification=globalThis.lablupNotification}_refreshHealthPanel(){this.activeConnected&&(this._refreshSessionInformation(),this.is_superadmin&&this._refreshAgentInformation())}_refreshSessionInformation(){if(!this.activeConnected)return;this.spinner.show();let t="RUNNING";switch(this.condition){case"running":case"archived":default:t="RUNNING";break;case"finished":t="TERMINATED"}globalThis.backendaiclient.computeSession.total_count(t).then((t=>{this.spinner.hide(),!t.compute_session_list&&t.legacy_compute_session_list&&(t.compute_session_list=t.legacy_compute_session_list),this.sessions=t.compute_session_list.total_count,this.active&&setTimeout((()=>{this._refreshSessionInformation()}),15e3)})).catch((t=>{this.spinner.hide(),this.sessions=0,this.notification.text=l("summary.ConnectingToCluster"),this.notification.detail=t,this.notification.show(!1,t),this.active&&setTimeout((()=>{this._refreshSessionInformation()}),15e3)}))}_refreshResourceInformation(){if(this.activeConnected)return globalThis.backendaiclient.resourcePolicy.get(globalThis.backendaiclient.resource_policy).then((t=>{const e=t.keypair_resource_policies;this.resourcePolicy=globalThis.backendaiclient.utils.gqlToObject(e,"name")}))}_refreshAgentInformation(t="running"){if(this.activeConnected){switch(this.condition){case"running":case"archived":default:t="ALIVE";break;case"finished":t="TERMINATED"}this.spinner.show(),globalThis.backendaiclient.resources.totalResourceInformation().then((e=>{this.spinner.hide(),this.resources=e,this._sync_resource_values(),1==this.active&&setTimeout((()=>{this._refreshAgentInformation(t)}),3e4)})).catch((t=>{this.spinner.hide(),t&&t.message&&(this.notification.text=h.relieve(t.title),this.notification.detail=t.message,this.notification.show(!0,t))}))}}_init_resource_values(){this.resources.cpu={},this.resources.cpu.total=0,this.resources.cpu.used=0,this.resources.cpu.percent=0,this.resources.mem={},this.resources.mem.total=0,this.resources.mem.allocated=0,this.resources.mem.used=0,this.resources.cuda_gpu={},this.resources.cuda_gpu.total=0,this.resources.cuda_gpu.used=0,this.resources.cuda_fgpu={},this.resources.cuda_fgpu.total=0,this.resources.cuda_fgpu.used=0,this.resources.rocm_gpu={},this.resources.rocm_gpu.total=0,this.resources.rocm_gpu.used=0,this.resources.tpu={},this.resources.tpu.total=0,this.resources.tpu.used=0,this.resources.ipu={},this.resources.ipu.total=0,this.resources.ipu.used=0,this.resources.atom={},this.resources.atom.total=0,this.resources.atom.used=0,this.resources.atom_plus={},this.resources.atom_plus.total=0,this.resources.atom_plus.used=0,this.resources.gaudi2={},this.resources.gaudi2.total=0,this.resources.gaudi2.used=0,this.resources.warboy={},this.resources.warboy.total=0,this.resources.warboy.used=0,this.resources.rngd={},this.resources.rngd.total=0,this.resources.rngd.used=0,this.resources.hyperaccel_lpu={},this.resources.hyperaccel_lpu.total=0,this.resources.hyperaccel_lpu.used=0,this.resources.agents={},this.resources.agents.total=0,this.resources.agents.using=0,this.cpu_total_usage_ratio=0,this.cpu_current_usage_ratio=0,this.mem_total_usage_ratio=0,this.mem_current_usage_ratio=0,this.mem_current_usage_percent="0",this.is_admin=!1,this.is_superadmin=!1}_sync_resource_values(){this.manager_version=globalThis.backendaiclient.managerVersion,this.webui_version=globalThis.packageVersion,this.cpu_total=this.resources.cpu.total,this.mem_total=parseFloat(globalThis.backendaiclient.utils.changeBinaryUnit(this.resources.mem.total,"g")).toFixed(2),isNaN(this.resources["cuda.device"].total)?this.cuda_gpu_total=0:this.cuda_gpu_total=this.resources["cuda.device"].total,isNaN(this.resources["cuda.shares"].total)?this.cuda_fgpu_total=0:this.cuda_fgpu_total=this.resources["cuda.shares"].total,isNaN(this.resources["rocm.device"].total)?this.rocm_gpu_total=0:this.rocm_gpu_total=this.resources["rocm.device"].total,isNaN(this.resources["tpu.device"].total)?this.tpu_total=0:this.tpu_total=this.resources["tpu.device"].total,isNaN(this.resources["ipu.device"].total)?this.ipu_total=0:this.ipu_total=this.resources["ipu.device"].total,isNaN(this.resources["atom.device"].total)?this.atom_total=0:this.atom_total=this.resources["atom.device"].total,isNaN(this.resources["atom-plus.device"].total)?this.atom_plus_total=0:this.atom_plus_total=this.resources["atom-plus.device"].total,isNaN(this.resources["gaudi2.device"].total)?this.gaudi2_total=0:this.gaudi2_total=this.resources["gaudi2.device"].total,isNaN(this.resources["warboy.device"].total)?this.warboy_total=0:this.warboy_total=this.resources["warboy.device"].total,isNaN(this.resources["rngd.device"].total)?this.rngd_total=0:this.rngd_total=this.resources["rngd.device"].total,isNaN(this.resources["hyperaccel-lpu.device"].total)?this.hyperaccel_lpu_total=0:this.hyperaccel_lpu_total=this.resources["hyperaccel-lpu.device"].total,this.cpu_used=this.resources.cpu.used,this.cuda_gpu_used=this.resources["cuda.device"].used,this.cuda_fgpu_used=this.resources["cuda.shares"].used,this.rocm_gpu_used=this.resources["rocm.device"].used,this.tpu_used=this.resources["tpu.device"].used,this.ipu_used=this.resources["ipu.device"].used,this.atom_used=this.resources["atom.device"].used,this.warboy_used=this.resources["warboy.device"].used,this.rngd_used=this.resources["rngd.device"].used,this.hyperaccel_lpu_used=this.resources["hyperaccel-lpu.device"].used,this.cpu_percent=parseFloat(this.resources.cpu.percent).toFixed(2),this.cpu_total_percent=0!==this.cpu_used?(this.cpu_used/this.cpu_total*100).toFixed(2):"0",this.cpu_total_usage_ratio=this.resources.cpu.used/this.resources.cpu.total*100,this.cpu_current_usage_ratio=this.resources.cpu.percent/this.resources.cpu.total,this.mem_used=parseFloat(globalThis.backendaiclient.utils.changeBinaryUnit(this.resources.mem.used,"g")).toFixed(2),this.mem_allocated=parseFloat(globalThis.backendaiclient.utils.changeBinaryUnit(this.resources.mem.allocated,"g")).toFixed(2),this.mem_total_usage_ratio=this.resources.mem.allocated/this.resources.mem.total*100,this.mem_current_usage_ratio=this.resources.mem.used/this.resources.mem.total*100,0===this.mem_total_usage_ratio?this.mem_current_usage_percent="0.0":this.mem_current_usage_percent=this.mem_total_usage_ratio.toFixed(2),this.agents=this.resources.agents.total,isNaN(parseFloat(this.mem_current_usage_percent))&&(this.mem_current_usage_percent="0")}async _viewStateChanged(t){await this.updateComplete,!1!==t&&(this._init_resource_values(),void 0===globalThis.backendaiclient||null===globalThis.backendaiclient||!1===globalThis.backendaiclient.ready?document.addEventListener("backend-ai-connected",(()=>{this.is_superadmin=globalThis.backendaiclient.is_superadmin,this.is_admin=globalThis.backendaiclient.is_admin,this.authenticated=!0,this.activeConnected&&(this._refreshHealthPanel(),this.requestUpdate())}),!0):(this.is_superadmin=globalThis.backendaiclient.is_superadmin,this.is_admin=globalThis.backendaiclient.is_admin,this.authenticated=!0,this._refreshHealthPanel(),this.requestUpdate()))}_toInt(t){return Math.ceil(t)}_countObject(t){return Object.keys(t).length}_addComma(t){if(void 0===t)return"";return t.toString().replace(/\B(?=(\d{3})+(?!\d))/g,",")}_prefixFormatWithoutTrailingZeros(t="0",e){const i="string"==typeof t?parseFloat(t):t;return parseFloat(i.toFixed(e)).toString()}_prefixFormat(t="0;",e){var i;return"string"==typeof t?null===(i=parseFloat(t))||void 0===i?void 0:i.toFixed(e):null==t?void 0:t.toFixed(e)}render(){return n`
      <link rel="stylesheet" href="resources/custom.css" />
      <lablup-loading-spinner id="loading-spinner"></lablup-loading-spinner>
      <lablup-activity-panel
        title="${m("summary.SystemResources")}"
        elevation="1"
        narrow
        height="${this.height}"
        scrollableY="true"
      >
        <div slot="message">
          <div class="horizontal justified layout wrap indicators">
            ${this.is_superadmin?n`
                  <div class="vertical layout center system-health-indicator">
                    <div class="big indicator">${this.agents}</div>
                    <span>${g("summary.ConnectedNodes")}</span>
                  </div>
                `:n``}
            <div class="vertical layout center system-health-indicator">
              <div class="big indicator">${this.sessions}</div>
              <span>${m("summary.ActiveSessions")}</span>
            </div>
          </div>
          <div class="vertical-card" style="align-items: flex-start">
            ${this.is_superadmin?n`
                  <div class="layout horizontal center flex resource">
                    <div
                      class="layout vertical center center-justified resource-name"
                    >
                      <div class="gauge-name">CPU</div>
                    </div>
                    <div class="layout vertical start-justified wrap">
                      <lablup-progress-bar
                        id="cpu-usage-bar"
                        class="start"
                        progress="${this.cpu_total_usage_ratio/100}"
                        description="${this._addComma(this._prefixFormatWithoutTrailingZeros(this.cpu_used,0))}/${this._addComma(this._prefixFormatWithoutTrailingZeros(this.cpu_total,0))} ${m("summary.CoresReserved")}."
                      ></lablup-progress-bar>
                      <lablup-progress-bar
                        id="cpu-usage-bar-2"
                        class="end"
                        progress="${this.cpu_current_usage_ratio/100}"
                        description="${m("summary.Using")} ${this._prefixFormatWithoutTrailingZeros(this.cpu_total_percent,1)} % (util. ${this._prefixFormatWithoutTrailingZeros(this.cpu_percent,1)} %)"
                      ></lablup-progress-bar>
                    </div>
                    <div class="layout vertical center center-justified">
                      <span class="percentage start-bar">
                        ${this._prefixFormatWithoutTrailingZeros(this.cpu_total_percent,1)+"%"}
                      </span>
                      <span class="percentage end-bar">
                        ${this._prefixFormatWithoutTrailingZeros(this.cpu_percent,1)+"%"}
                      </span>
                    </div>
                  </div>
                  <div class="resource-line"></div>
                  <div class="layout horizontal center flex resource">
                    <div
                      class="layout vertical center center-justified resource-name"
                    >
                      <div class="gauge-name">RAM</div>
                    </div>
                    <div class="layout vertical start-justified wrap">
                      <lablup-progress-bar
                        id="mem-usage-bar"
                        class="start"
                        progress="${this.mem_total_usage_ratio/100}"
                        description="${this._addComma(this._prefixFormatWithoutTrailingZeros(this.mem_allocated,2))} / ${this._addComma(this._prefixFormatWithoutTrailingZeros(this.mem_total,2))} GiB ${m("summary.ReservedShort")}."
                      ></lablup-progress-bar>
                      <lablup-progress-bar
                        id="mem-usage-bar-2"
                        class="end"
                        progress="${this.mem_current_usage_ratio/100}"
                        description="${m("summary.Using")} ${this._addComma(this._prefixFormatWithoutTrailingZeros(this.mem_used,2))} GiB
                    (${0!==parseInt(this.mem_used)?this._prefixFormatWithoutTrailingZeros(parseInt(this.mem_used)/parseInt(this.mem_total)*100,1):"0"} %)"
                      ></lablup-progress-bar>
                    </div>
                    <div class="layout vertical center center-justified">
                      <span class="percentage start-bar">
                        ${this._prefixFormatWithoutTrailingZeros(this.mem_total_usage_ratio,1)+"%"}
                      </span>
                      <span class="percentage end-bar">
                        ${(0!==parseInt(this.mem_used)?this._prefixFormatWithoutTrailingZeros(parseInt(this.mem_used)/parseInt(this.mem_total)*100,1):"0")+"%"}
                      </span>
                    </div>
                  </div>
                  ${this.cuda_gpu_total||this.cuda_fgpu_total||this.rocm_gpu_total||this.tpu_total||this.ipu_total||this.atom_total||this.atom_plus_total||this.gaudi2_total||this.warboy_total||this.rngd_total||this.hyperaccel_lpu_total?n`
                        <div class="resource-line"></div>
                        <div class="layout horizontal center flex resource">
                          <div
                            class="layout vertical center center-justified resource-name"
                          >
                            <div class="gauge-name">GPU / NPU</div>
                          </div>
                          <div class="layout vertical">
                            ${this.cuda_gpu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="gpu-usage-bar"
                                        class="start"
                                        progress="${this.cuda_gpu_used/this.cuda_gpu_total}"
                                        description="${this._prefixFormat(this.cuda_gpu_used,2)} / ${this._prefixFormat(this.cuda_gpu_total,2)} CUDA GPUs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="gpu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.FractionalGPUScalingEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${0!==this.cuda_gpu_used?this._prefixFormatWithoutTrailingZeros(this.cuda_gpu_used/this.cuda_gpu_total*100,1):0}%
                                      </span>
                                      <span class="percentage end-bar">
                                        &nbsp;
                                      </span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.cuda_fgpu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="fgpu-usage-bar"
                                        class="start"
                                        progress="${this.cuda_fgpu_used/this.cuda_fgpu_total}"
                                        description="${this._prefixFormat(this.cuda_fgpu_used,2)} / ${this._prefixFormat(this.cuda_fgpu_total,2)} CUDA FGPUs ${m("summary.Reserved")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="fgpu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.FractionalGPUScalingEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${0!==this.cuda_fgpu_used?this._prefixFormatWithoutTrailingZeros(this.cuda_fgpu_used/this.cuda_fgpu_total*100,1):0}%
                                      </span>
                                      <span class="percentage end-bar">
                                        &nbsp;
                                      </span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.rocm_gpu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="rocm-gpu-usage-bar"
                                        class="start"
                                        progress="${this.rocm_gpu_used/100}"
                                        description="${this._prefixFormat(this.rocm_gpu_used,2)} / ${this._prefixFormat(this.rocm_gpu_total,2)} ROCm GPUs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="rocm-gpu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.ROCMGPUEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.rocm_gpu_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar">
                                        &nbsp;
                                      </span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.tpu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="tpu-usage-bar"
                                        class="start"
                                        progress="${this.tpu_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.tpu_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.tpu_total,2)} TPUs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="tpu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.TPUEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.tpu_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.ipu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="ipu-usage-bar"
                                        class="start"
                                        progress="${this.ipu_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.ipu_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.ipu_total,2)} IPUs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="ipu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.IPUEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.ipu_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.atom_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="atom-usage-bar"
                                        class="start"
                                        progress="${this.atom_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.atom_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.atom_total,2)} ATOMs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="atom-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.ATOMEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.atom_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.atom_plus_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="atom-plus-usage-bar"
                                        class="start"
                                        progress="${this.atom_plus_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.atom_plus_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.atom_plus_total,2)} ATOM+ ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="atom-plus-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.ATOMPlusEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.atom_plus_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.gaudi2_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="gaudi-2-usage-bar"
                                        class="start"
                                        progress="${this.gaudi2_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.gaudi2_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.gaudi2_total,2)} Gaudi 2 ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="gaudi-2-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("session.Gaudi2Enabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.gaudi2_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.warboy_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="warboy-usage-bar"
                                        class="start"
                                        progress="${this.warboy_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.warboy_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.warboy_total,2)} Warboys ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="warboy-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.WarboyEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.warboy_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.rngd_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="rngd-usage-bar"
                                        class="start"
                                        progress="${this.rngd_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.rngd_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.rngd_total,2)} RNGDs ${m("summary.ReservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="rngd-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.RNGDEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.rngd_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                            ${this.hyperaccel_lpu_total?n`
                                  <div class="layout horizontal">
                                    <div
                                      class="layout vertical start-justified wrap"
                                    >
                                      <lablup-progress-bar
                                        id="hyperaccel-lpu-usage-bar"
                                        class="start"
                                        progress="${this.hyperaccel_lpu_used/100}"
                                        description="${this._prefixFormatWithoutTrailingZeros(this.hyperaccel_lpu_used,2)} / ${this._prefixFormatWithoutTrailingZeros(this.hyperaccel_lpu_total,2)} Hyperaccel LPUs ${m("summary.reservedShort")}."
                                      ></lablup-progress-bar>
                                      <lablup-progress-bar
                                        id="hyperaccel-lpu-usage-bar-2"
                                        class="end"
                                        progress="0"
                                        description="${m("summary.HyperaccelLPUEnabled")}."
                                      ></lablup-progress-bar>
                                    </div>
                                    <div
                                      class="layout vertical center center-justified"
                                    >
                                      <span class="percentage start-bar">
                                        ${this._prefixFormatWithoutTrailingZeros(this.hyperaccel_lpu_used,1)+"%"}
                                      </span>
                                      <span class="percentage end-bar"></span>
                                    </div>
                                  </div>
                                `:n``}
                          </div>
                        </div>
                      `:n``}
                  <div class="vertical start layout" style="margin-top:30px;">
                    <div class="horizontal layout resource-legend-stack">
                      <div class="resource-legend-icon start"></div>
                      <span class="resource-legend">
                        ${m("summary.Reserved")}
                        ${m("resourcePolicy.Resources")}
                      </span>
                    </div>
                    <div class="horizontal layout resource-legend-stack">
                      <div class="resource-legend-icon end"></div>
                      <span class="resource-legend">
                        ${m("summary.Used")} ${m("resourcePolicy.Resources")}
                      </span>
                    </div>
                    <div class="horizontal layout">
                      <div class="resource-legend-icon total"></div>
                      <span class="resource-legend">
                        ${m("summary.Total")} ${m("resourcePolicy.Resources")}
                      </span>
                    </div>
                  </div>
                `:n``}
          </div>
        </div>
      </lablup-activity-panel>
    `}};var w;t([e({type:String})],x.prototype,"condition",void 0),t([e({type:Number})],x.prototype,"sessions",void 0),t([e({type:Number})],x.prototype,"agents",void 0),t([e({type:Boolean})],x.prototype,"is_admin",void 0),t([e({type:Boolean})],x.prototype,"is_superadmin",void 0),t([e({type:Object})],x.prototype,"resources",void 0),t([e({type:Boolean})],x.prototype,"authenticated",void 0),t([e({type:String})],x.prototype,"manager_version",void 0),t([e({type:String})],x.prototype,"webui_version",void 0),t([e({type:Number})],x.prototype,"cpu_total",void 0),t([e({type:Number})],x.prototype,"cpu_used",void 0),t([e({type:String})],x.prototype,"cpu_percent",void 0),t([e({type:String})],x.prototype,"cpu_total_percent",void 0),t([e({type:Number})],x.prototype,"cpu_total_usage_ratio",void 0),t([e({type:Number})],x.prototype,"cpu_current_usage_ratio",void 0),t([e({type:String})],x.prototype,"mem_total",void 0),t([e({type:String})],x.prototype,"mem_used",void 0),t([e({type:String})],x.prototype,"mem_allocated",void 0),t([e({type:Number})],x.prototype,"mem_total_usage_ratio",void 0),t([e({type:Number})],x.prototype,"mem_current_usage_ratio",void 0),t([e({type:String})],x.prototype,"mem_current_usage_percent",void 0),t([e({type:Number})],x.prototype,"cuda_gpu_total",void 0),t([e({type:Number})],x.prototype,"cuda_gpu_used",void 0),t([e({type:Number})],x.prototype,"cuda_fgpu_total",void 0),t([e({type:Number})],x.prototype,"cuda_fgpu_used",void 0),t([e({type:Number})],x.prototype,"rocm_gpu_total",void 0),t([e({type:Number})],x.prototype,"rocm_gpu_used",void 0),t([e({type:Number})],x.prototype,"tpu_total",void 0),t([e({type:Number})],x.prototype,"tpu_used",void 0),t([e({type:Number})],x.prototype,"ipu_total",void 0),t([e({type:Number})],x.prototype,"ipu_used",void 0),t([e({type:Number})],x.prototype,"atom_total",void 0),t([e({type:Number})],x.prototype,"atom_used",void 0),t([e({type:Number})],x.prototype,"atom_plus_total",void 0),t([e({type:Number})],x.prototype,"atom_plus_used",void 0),t([e({type:Number})],x.prototype,"gaudi2_total",void 0),t([e({type:Number})],x.prototype,"gaudi2_used",void 0),t([e({type:Number})],x.prototype,"warboy_total",void 0),t([e({type:Number})],x.prototype,"warboy_used",void 0),t([e({type:Number})],x.prototype,"rngd_total",void 0),t([e({type:Number})],x.prototype,"rngd_used",void 0),t([e({type:Number})],x.prototype,"hyperaccel_lpu_total",void 0),t([e({type:Number})],x.prototype,"hyperaccel_lpu_used",void 0),t([e({type:Object})],x.prototype,"notification",void 0),t([e({type:Object})],x.prototype,"resourcePolicy",void 0),t([e({type:String})],x.prototype,"announcement",void 0),t([e({type:Number})],x.prototype,"height",void 0),t([p("#loading-spinner")],x.prototype,"spinner",void 0),x=t([i("backend-ai-resource-panel")],x);let $=w=class extends c{constructor(){super(),this.condition="running",this.sessions=0,this.jobs=Object(),this.agents=0,this.is_admin=!1,this.is_superadmin=!1,this.resources=Object(),this.update_checker=Object(),this.authenticated=!1,this.manager_version="",this.webui_version="",this.cpu_total=0,this.cpu_used=0,this.cpu_percent="0",this.cpu_total_percent="0",this.cpu_total_usage_ratio=0,this.cpu_current_usage_ratio=0,this.mem_total="0",this.mem_used="0",this.mem_allocated="0",this.mem_total_usage_ratio=0,this.mem_current_usage_ratio=0,this.mem_current_usage_percent="0",this.cuda_gpu_total=0,this.cuda_gpu_used=0,this.cuda_fgpu_total=0,this.cuda_fgpu_used=0,this.rocm_gpu_total=0,this.rocm_gpu_used=0,this.tpu_total=0,this.tpu_used=0,this.ipu_total=0,this.ipu_used=0,this.atom_total=0,this.atom_used=0,this.notification=Object(),this.invitations=Object(),this.allowAppDownloadPanel=!0,this.downloadAppOS="",this.invitations=[],this.appDownloadMap={Linux:{os:"linux",architecture:["arm64","x64"],extension:"zip"},MacOS:{os:"macos",architecture:["arm64","x64"],extension:"dmg"},Windows:{os:"win32",architecture:["arm64","x64"],extension:"zip"}}}static get styles(){return[u,a,r,d,o`
        ul {
          padding-left: 0;
        }

        ul li {
          list-style: none;
          font-size: 14px;
        }

        li:before {
          padding: 3px;
          transform: rotate(-45deg) translateY(-2px);
          transition: color ease-in 0.2s;
          border: solid;
          border-width: 0 2px 2px 0;
          border-color: #242424;
          margin-right: 10px;
          content: '';
          display: inline-block;
        }

        span.indicator {
          width: 100px;
        }

        div.big.indicator {
          font-size: 48px;
        }

        #session-launcher {
          --component-width: 284px;
        }

        .start-menu-items {
          margin-top: 20px;
          width: 100px;
        }

        .start-menu-items span {
          padding-left: 10px;
          padding-right: 10px;
          text-align: center;
        }

        .invitation_folder_name {
          font-size: 13px;
        }

        mwc-icon-button.update-button {
          --mdc-icon-size: 16px;
          --mdc-icon-button-size: 24px;
          color: red;
        }

        a > i {
          color: #5b5b5b;
          margin: 10px;
        }

        a > span {
          max-width: 70px;
          color: #838383;
        }

        mwc-icon.update-icon {
          --mdc-icon-size: 16px;
          --mdc-icon-button-size: 24px;
          color: black;
        }

        img.resource-type-icon {
          width: 16px;
          height: 16px;
          margin-right: 5px;
        }

        .system-health-indicator {
          width: 90px;
        }

        .upper-lower-space {
          padding-top: 20px;
          padding-bottom: 10px;
        }

        i.larger {
          font-size: 1.2rem;
        }

        .left-end-icon {
          margin-left: 11px;
          margin-right: 12px;
        }

        .right-end-icon {
          margin-left: 12px;
          margin-right: 11px;
        }

        #download-app-os-select-box {
          height: 80px;
          padding-top: 20px;
          background-color: var(--token-colorBgContainer, #f6f6f6);
          margin-bottom: var(--token-marginSM);
        }

        #download-app-os-select-box mwc-select {
          width: 100%;
          height: 58px;
        }

        lablup-activity-panel.inner-panel:hover {
          --card-background-color: var(--general-background-color);
        }

        @media screen and (max-width: 750px) {
          lablup-activity-panel.footer-menu > div > a > div > span {
            text-align: left;
            width: 250px;
          }
        }

        button.link-button {
          background: none;
          color: var(--token-colorTextSecondary);
          border: none;
          padding: 0;
          font: inherit;
          cursor: pointer;
          outline: inherit;
        }
        button.link-button > i {
          color: var(--token-colorTextSecondary, #5b5b5b);
          margin: 10px;
        }
        button.link-button > span {
          max-width: 70px;
          color: var(--token-colorTextSecondary, #838383);
        }
        button.link-button:hover {
          color: var(--token-colorPrimary, #3e872d);
        }
      `]}firstUpdated(){var t;this.notification=globalThis.lablupNotification,this.update_checker=null===(t=this.shadowRoot)||void 0===t?void 0:t.querySelector("#update-checker"),this._getUserOS()}_getUserOS(){this.downloadAppOS="MacOS",-1!=navigator.userAgent.indexOf("Mac")&&(this.downloadAppOS="MacOS"),-1!=navigator.userAgent.indexOf("Win")&&(this.downloadAppOS="Windows"),-1!=navigator.userAgent.indexOf("Linux")&&(this.downloadAppOS="Linux")}_refreshConsoleUpdateInformation(){this.is_superadmin&&globalThis.backendaioptions.get("automatic_update_check",!0)&&this.update_checker.checkRelease()}async _viewStateChanged(t){if(await this.updateComplete,!1===t)return this.resourceMonitor.removeAttribute("active"),void this.resourcePanel.removeAttribute("active");this.resourceMonitor.setAttribute("active","true"),this.resourcePanel.setAttribute("active",""),void 0===globalThis.backendaiclient||null===globalThis.backendaiclient||!1===globalThis.backendaiclient.ready?document.addEventListener("backend-ai-connected",(()=>{this.is_superadmin=globalThis.backendaiclient.is_superadmin,this.is_admin=globalThis.backendaiclient.is_admin,this.authenticated=!0,this.manager_version=globalThis.backendaiclient.managerVersion,this.webui_version=globalThis.packageVersion,this.appDownloadUrl=globalThis.backendaiclient._config.appDownloadUrl,this.allowAppDownloadPanel=globalThis.backendaiclient._config.allowAppDownloadPanel,globalThis.backendaiclient.supports("use-win-instead-of-win32")&&(this.appDownloadMap.Windows.os="win"),this.activeConnected&&this._refreshConsoleUpdateInformation(),this._refreshInvitations()}),!0):(this.is_superadmin=globalThis.backendaiclient.is_superadmin,this.is_admin=globalThis.backendaiclient.is_admin,this.authenticated=!0,this.manager_version=globalThis.backendaiclient.managerVersion,this.webui_version=globalThis.packageVersion,this.appDownloadUrl=globalThis.backendaiclient._config.appDownloadUrl,this.allowAppDownloadPanel=globalThis.backendaiclient._config.allowAppDownloadPanel,globalThis.backendaiclient.supports("use-win-instead-of-win32")&&(this.appDownloadMap.Windows.os="win"),this._refreshConsoleUpdateInformation(),this._refreshInvitations())}_toInt(t){return Math.ceil(t)}_countObject(t){return Object.keys(t).length}_addComma(t){if(void 0===t)return"";return t.toString().replace(/\B(?=(\d{3})+(?!\d))/g,",")}_refreshInvitations(t=!1){this.activeConnected&&globalThis.backendaiclient.vfolder.invitations().then((e=>{this.invitations=e.invitations,this.active&&!t&&setTimeout((()=>{this._refreshInvitations()}),6e4)}))}static getVFolderTabByVFolderInfo(t){return t.name.startsWith(".")||"model"!=t.usage_mode?t.name.startsWith(".")||"general"!=t.usage_mode?t.name.startsWith(".")||"data"!=t.usage_mode?t.name.startsWith(".")?"automount":"general":"data":"general":"model"}async _acceptInvitation(t,e){if(this.activeConnected){try{await globalThis.backendaiclient.vfolder.accept_invitation(e.id);const t=globalThis.backendaiclient.supports("vfolder-id-based")?e.vfolder_id:e.vfolder_name,i=await globalThis.backendaiclient.vfolder.info(t),s=w.getVFolderTabByVFolderInfo(i);this.notification.url=`/data?tab=${s}&folder=${e.vfolder_id.replace("-","")}`,this.notification.text=l("summary.AcceptSharedVFolder")+`${e.vfolder_name}`,this.notification.show(!0)}catch(t){this.notification.text=h.relieve(t.title),this.notification.detail=t.message,this.notification.show(!0,t)}this._refreshInvitations()}}async _deleteInvitation(t,e){if(this.activeConnected){try{await globalThis.backendaiclient.vfolder.delete_invitation(e.id),this.notification.text=l("summary.DeclineSharedVFolder")+`${e.vfolder_name}`,this.notification.show()}catch(t){this.notification.text=h.relieve(t.title),this.notification.detail=t.message,this.notification.show(!0,t)}this._refreshInvitations()}}_stripHTMLTags(t){return t.replace(/(<([^>]+)>)/gi,"")}_updateSelectedDownloadAppOS(t){this.downloadAppOS=t.target.value}_downloadApplication(t){let e="";const i=t.target.innerText.toLowerCase(),s=globalThis.packageVersion,a=this.appDownloadMap[this.downloadAppOS].os,r=this.appDownloadMap[this.downloadAppOS].extension;e=`${this.appDownloadUrl}/v${s}/backend.ai-desktop-${s}-${a}-${i}.${r}`,window.open(e,"_blank")}_moveTo(t="",e=void 0){const i=""!==t?t:"start";_.dispatch(v(decodeURIComponent(i),{})),document.dispatchEvent(new CustomEvent("react-navigate",{detail:{pathname:t,search:e}}))}render(){return n`
      <link rel="stylesheet" href="/resources/fonts/font-awesome-all.min.css" />
      <link rel="stylesheet" href="resources/custom.css" />
      <div class="item" elevation="1" class="vertical layout center flex">
        <div class="horizontal wrap layout" style="gap:24px;">
          <lablup-activity-panel
            title="${m("summary.ResourceStatistics")}"
            elevation="1"
            narrow
            height="500"
            scrollableY="true"
          >
            <div slot="message">
              <backend-ai-resource-monitor
                location="summary"
                id="resource-monitor"
                ?active="${!0===this.active}"
                direction="vertical"
              ></backend-ai-resource-monitor>
            </div>
          </lablup-activity-panel>
          <backend-ai-resource-panel
            id="resource-panel"
            ?active="${!0===this.active}"
            height="500"
          ></backend-ai-resource-panel>

          <!-- Vertical container for the two 245px panels -->
          <div class="vertical layout" style="gap:10px;">
            <lablup-activity-panel
              title="${m("summary.Invitation")}"
              elevation="1"
              narrow
              height="245"
              scrollableY="true"
            >
              <div
                class="layout vertical"
                slot="message"
                style="padding: 10px; gap: 10px;"
              >
                ${this.invitations.length>0?this.invitations.map(((t,e)=>n`
                        <lablup-activity-panel
                          class="inner-panel"
                          noheader
                          autowidth
                          elevation="1"
                          height="130"
                        >
                          <div slot="message">
                            <div class="wrap layout">
                              <h3 style="padding-top:10px;">
                                From ${t.inviter}
                              </h3>
                              <div class="invitation_folder_name">
                                ${m("summary.FolderName")}:
                                ${t.vfolder_name}
                              </div>
                              <div class="horizontal center layout">
                                ${m("summary.Permission")}:
                                ${[...t.perm].map((t=>n`
                                    <lablup-shields
                                      app=""
                                      color="${["green","blue","red","yellow"][["r","w","d","o"].indexOf(t)]}"
                                      description="${t.toUpperCase()}"
                                      ui="flat"
                                    ></lablup-shields>
                                  `))}
                              </div>
                              <div
                                style="margin:15px auto; gap: 8px;"
                                class="horizontal layout end-justified"
                              >
                                <mwc-button
                                  outlined
                                  label="${m("summary.Decline")}"
                                  @click="${e=>this._deleteInvitation(e,t)}"
                                ></mwc-button>
                                <mwc-button
                                  unelevated
                                  label="${m("summary.Accept")}"
                                  @click="${e=>this._acceptInvitation(e,t)}"
                                ></mwc-button>
                                <span class="flex"></span>
                              </div>
                            </div>
                          </div>
                        </lablup-activity-panel>
                      `)):n`
                      <p>${l("summary.NoInvitations")}</p>
                    `}
              </div>
            </lablup-activity-panel>

            ${!globalThis.isElectron&&this.allowAppDownloadPanel?n`
                  <lablup-activity-panel
                    title="${m("summary.DownloadWebUIApp")}"
                    elevation=""
                    height="245"
                  >
                    <div slot="message">
                      <div
                        id="download-app-os-select-box"
                        class="horizontal layout center-justified"
                      >
                        <mwc-select
                          outlined
                          @selected="${t=>this._updateSelectedDownloadAppOS(t)}"
                        >
                          ${Object.keys(this.appDownloadMap).map((t=>n`
                              <mwc-list-item
                                value="${t}"
                                ?selected="${t===this.downloadAppOS}"
                              >
                                ${t}
                              </mwc-list-item>
                            `))}
                        </mwc-select>
                      </div>
                      <div
                        class="horizontal layout center-justified"
                        style="gap:20px"
                      >
                        ${this.downloadAppOS&&this.appDownloadMap[this.downloadAppOS].architecture.map((t=>n`
                            <mwc-button
                              icon="cloud_download"
                              outlined
                              style="margin:10px 0 10px 0;flex-basis:50%;"
                              @click="${t=>this._downloadApplication(t)}"
                            >
                              ${t}
                            </mwc-button>
                          `))}
                      </div>
                    </div>
                  </lablup-activity-panel>
                `:n``}
          </div>
        </div>
        <div class="vertical layout">
          ${this.is_admin?n`
              <div class="horizontal layout wrap">
                <div class="vertical layout">
                  <div class="line"></div>
                  <div class="horizontal layout flex wrap center-justified" style="gap:24px;">
                    <lablup-activity-panel class="footer-menu" noheader autowidth style="display: none;">
                      <div slot="message" class="vertical layout center start-justified flex upper-lower-space">
                        <h3 style="margin-top:0px;">${m("summary.CurrentVersion")}</h3>
                        ${this.is_superadmin?n`
                                <div
                                  class="layout vertical center center-justified flex"
                                  style="margin-bottom:5px;"
                                >
                                  <lablup-shields
                                    app="Manager version"
                                    color="darkgreen"
                                    description="${this.manager_version}"
                                    ui="flat"
                                  ></lablup-shields>
                                  <div
                                    class="layout horizontal center flex"
                                    style="margin-top:4px;"
                                  >
                                    <lablup-shields
                                      app="Console version"
                                      color="${this.update_checker.updateNeeded?"red":"darkgreen"}"
                                      description="${this.webui_version}"
                                      ui="flat"
                                    ></lablup-shields>
                                    ${this.update_checker.updateNeeded?n`
                                          <mwc-icon-button
                                            class="update-button"
                                            icon="new_releases"
                                            @click="${()=>{window.open(this.update_checker.updateURL,"_blank")}}"
                                          ></mwc-icon-button>
                                        `:n`
                                          <mwc-icon class="update-icon">
                                            done
                                          </mwc-icon>
                                        `}
                                  </div>
                                </div>
                              `:n``}
                      </div>
                    </lablup-activity-panel>
                    <lablup-activity-panel class="footer-menu" noheader autowidth>
                      <div slot="message" class="layout horizontal center center-justified flex upper-lower-space">
                          <button class="link-button" @click="${()=>{this._moveTo("/environment")}}" >
                            <div class="layout horizontal center center-justified flex"  style="font-size:14px;">
                              <i class="fas fa-sync-alt larger left-end-icon"></i>
                              <span>${m("summary.UpdateEnvironmentImages")}</span>
                              <i class="fas fa-chevron-right right-end-icon"></i>
                            </div>
                          </button>
                      </div>
                    </lablup-activity-panel>
                    ${this.is_superadmin?n`
                            <lablup-activity-panel
                              class="footer-menu"
                              noheader
                              autowidth
                            >
                              <div
                                slot="message"
                                class="layout horizontal center center-justified flex upper-lower-space"
                              >
                                <button
                                  class="link-button"
                                  @click="${()=>this._moveTo("/agent")}"
                                >
                                  <div
                                    class="layout horizontal center center-justified flex"
                                    style="font-size:14px;"
                                  >
                                    <i
                                      class="fas fa-box larger left-end-icon"
                                    ></i>
                                    <span>${m("summary.CheckResources")}</span>
                                    <i
                                      class="fas fa-chevron-right right-end-icon"
                                    ></i>
                                  </div>
                                </button>
                              </div>
                            </lablup-activity-panel>
                            <lablup-activity-panel
                              class="footer-menu"
                              noheader
                              autowidth
                            >
                              <div
                                slot="message"
                                class="layout horizontal center center-justified flex upper-lower-space"
                              >
                                <button
                                  class="link-button"
                                  @click="${()=>this._moveTo("settings")}"
                                >
                                  <div
                                    class="layout horizontal center center-justified flex"
                                    style="font-size:14px;"
                                  >
                                    <i
                                      class="fas fa-desktop larger left-end-icon"
                                    ></i>
                                    <span>
                                      ${m("summary.ChangeSystemSetting")}
                                    </span>
                                    <i
                                      class="fas fa-chevron-right right-end-icon"
                                    ></i>
                                  </div>
                                </button>
                              </div>
                            </lablup-activity-panel>
                          `:n``}
                    ${this.is_superadmin?n`
                            <lablup-activity-panel
                              class="footer-menu"
                              noheader
                              autowidth
                            >
                              <div
                                slot="message"
                                class="layout horizontal center center-justified flex upper-lower-space"
                              >
                                <button
                                  class="link-button"
                                  @click="${()=>this._moveTo("/maintenance")}"
                                >
                                  <div
                                    class="layout horizontal center center-justified flex"
                                    style="font-size:14px;"
                                  >
                                    <i
                                      class="fas fa-tools larger left-end-icon"
                                    ></i>
                                    <span>
                                      ${m("summary.SystemMaintenance")}
                                    </span>
                                    <i
                                      class="fas fa-chevron-right right-end-icon"
                                    ></i>
                                  </div>
                                </button>
                              </div>
                            </lablup-activity-panel>
                          `:n``}
                  </div>
                </div>
              </div>
          </div>`:n``}
        </div>
      </div>
      <backend-ai-release-check id="update-checker"></backend-ai-release-check>
    `}};t([e({type:String})],$.prototype,"condition",void 0),t([e({type:Number})],$.prototype,"sessions",void 0),t([e({type:Object})],$.prototype,"jobs",void 0),t([e({type:Number})],$.prototype,"agents",void 0),t([e({type:Boolean})],$.prototype,"is_admin",void 0),t([e({type:Boolean})],$.prototype,"is_superadmin",void 0),t([e({type:Object})],$.prototype,"resources",void 0),t([e({type:Object})],$.prototype,"update_checker",void 0),t([e({type:Boolean})],$.prototype,"authenticated",void 0),t([e({type:String})],$.prototype,"manager_version",void 0),t([e({type:String})],$.prototype,"webui_version",void 0),t([e({type:Number})],$.prototype,"cpu_total",void 0),t([e({type:Number})],$.prototype,"cpu_used",void 0),t([e({type:String})],$.prototype,"cpu_percent",void 0),t([e({type:String})],$.prototype,"cpu_total_percent",void 0),t([e({type:Number})],$.prototype,"cpu_total_usage_ratio",void 0),t([e({type:Number})],$.prototype,"cpu_current_usage_ratio",void 0),t([e({type:String})],$.prototype,"mem_total",void 0),t([e({type:String})],$.prototype,"mem_used",void 0),t([e({type:String})],$.prototype,"mem_allocated",void 0),t([e({type:Number})],$.prototype,"mem_total_usage_ratio",void 0),t([e({type:Number})],$.prototype,"mem_current_usage_ratio",void 0),t([e({type:String})],$.prototype,"mem_current_usage_percent",void 0),t([e({type:Number})],$.prototype,"cuda_gpu_total",void 0),t([e({type:Number})],$.prototype,"cuda_gpu_used",void 0),t([e({type:Number})],$.prototype,"cuda_fgpu_total",void 0),t([e({type:Number})],$.prototype,"cuda_fgpu_used",void 0),t([e({type:Number})],$.prototype,"rocm_gpu_total",void 0),t([e({type:Number})],$.prototype,"rocm_gpu_used",void 0),t([e({type:Number})],$.prototype,"tpu_total",void 0),t([e({type:Number})],$.prototype,"tpu_used",void 0),t([e({type:Number})],$.prototype,"ipu_total",void 0),t([e({type:Number})],$.prototype,"ipu_used",void 0),t([e({type:Number})],$.prototype,"atom_total",void 0),t([e({type:Number})],$.prototype,"atom_used",void 0),t([e({type:Object})],$.prototype,"notification",void 0),t([e({type:Object})],$.prototype,"resourcePolicy",void 0),t([e({type:Object})],$.prototype,"invitations",void 0),t([e({type:Object})],$.prototype,"appDownloadMap",void 0),t([e({type:String})],$.prototype,"appDownloadUrl",void 0),t([e({type:Boolean})],$.prototype,"allowAppDownloadPanel",void 0),t([e({type:String})],$.prototype,"downloadAppOS",void 0),t([p("#resource-monitor")],$.prototype,"resourceMonitor",void 0),t([p("#resource-panel")],$.prototype,"resourcePanel",void 0),$=w=t([i("backend-ai-summary-view")],$);var k=$;export{k as default};
