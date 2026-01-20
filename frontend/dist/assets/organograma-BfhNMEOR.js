import{a as t,j as e,c as $}from"./index-Q695sD3D.js";const L=t.createContext({hoveredNodeId:null,setHoveredNodeId:()=>{}}),M=r=>{if(!r)return"#64748b";const s={Financeiro:"#059669",Comercial:"#d97706",Vendas:"#d97706",TI:"#2563eb",Tecnologia:"#2563eb","Recursos Humanos":"#db2777",RH:"#db2777",Diretoria:"#0f172a",Executivo:"#0f172a",Jurídico:"#7c3aed",Marketing:"#ea580c",Operações:"#0891b2"};if(s[r])return s[r];let l=0;for(let d=0;d<r.length;d++)l=r.charCodeAt(d)+((l<<5)-l);return`hsl(${Math.abs(l%360)}, 60%, 40%)`},H=r=>{if(!r)return"";const s=r.split(" ");return s.length>=2?`${s[0][0]}${s[s.length-1][0]}`.toUpperCase():r[0].toUpperCase()},A=({node:r,isExpanded:s,toggleNode:l,hasChildren:p,isMatch:d,parentId:v})=>{const{hoveredNodeId:n,setHoveredNodeId:g}=t.useContext(L),i=t.useMemo(()=>M(r.department),[r.department]),x=r.distinguishedName,u=n===x,h=n===v&&n!==null,m=n!==null&&!u&&!h,b=r.title&&(r.title.toLowerCase().includes("presidente")||r.title.toLowerCase().includes("ceo")||r.title.toLowerCase().includes("diretor")),w=j=>{j.stopPropagation(),g(x)},y=()=>{g(null)};return e.jsxs("div",{className:`
                org-card
                ${d?"highlight":""}
                ${b?"executive":""}
                ${u?"state-active":""}
                ${h?"state-subordinate":""}
                ${m?"state-dimmed":""}
            `,onClick:()=>p&&l(),onMouseEnter:w,onMouseLeave:y,style:{"--dept-color":i},children:[e.jsx("div",{className:"card-accent",style:{backgroundColor:i}}),e.jsxs("div",{className:"card-body",children:[e.jsxs("div",{className:"card-header",children:[e.jsx("div",{className:"avatar",style:{backgroundColor:b?"#0f172a":`${i}15`,color:b?"#fff":i},children:H(r.name)}),e.jsxs("div",{className:"info",children:[e.jsx("h6",{className:"name",title:r.name,children:r.name}),e.jsx("p",{className:"role",title:r.title,children:r.title||"Cargo não definido"})]})]}),r.department&&e.jsx("div",{className:"card-footer",children:e.jsx("span",{className:"dept-badge",style:{color:i,borderColor:`${i}30`},children:r.department})})]}),p&&e.jsx("div",{className:`toggle-btn ${s?"expanded":""}`,children:e.jsx("i",{className:"fas fa-chevron-down"})})]})},D=()=>{const[r,s]=t.useState([]),[l,p]=t.useState(!0),[d,v]=t.useState(null),[n,g]=t.useState(""),[i,x]=t.useState(1),[u,h]=t.useState(new Set),[m,b]=t.useState(null);t.useEffect(()=>{fetch("/api/public/organogram_data").then(a=>{if(!a.ok)throw new Error("Falha ao carregar dados");return a.json()}).then(a=>{const c=Array.isArray(a)?a:[];s(c);const o=new Set;c.forEach((N,k)=>{const f=N.distinguishedName||k;o.add(f)}),h(o),p(!1)}).catch(a=>{v(a.message),p(!1)})},[]);const w=a=>{h(c=>{const o=new Set(c);return o.has(a)?o.delete(a):o.add(a),o})},y=()=>x(a=>Math.min(a+.1,2)),j=()=>x(a=>Math.max(a-.1,.4)),E=()=>x(1),C=(a,c=null)=>!a||!Array.isArray(a)||a.length===0?null:e.jsx("ul",{className:"org-tree",children:a.map((o,N)=>{const k=n&&o.name&&o.name.toLowerCase().includes(n.toLowerCase()),f=o.distinguishedName||N,z=o.children&&o.children.length>0,S=u.has(f),I=m===c&&m!==null;return e.jsxs("li",{className:`org-leaf ${I?"conn-active":""}`,children:[e.jsx(A,{node:o,isExpanded:S,toggleNode:()=>w(f),hasChildren:z,isMatch:k,parentId:c}),z&&S&&C(o.children,f)]},f)})});return l?e.jsxs("div",{className:"loading-container",children:[e.jsx("div",{className:"spinner"}),e.jsx("p",{children:"Carregando estrutura..."})]}):d?e.jsxs("div",{className:"error-container",children:[e.jsx("i",{className:"fas fa-exclamation-triangle"}),e.jsxs("p",{children:["Erro ao carregar: ",d]})]}):e.jsx(L.Provider,{value:{hoveredNodeId:m,setHoveredNodeId:b},children:e.jsxs("div",{className:"organogram-page",children:[e.jsxs("header",{className:"page-header",children:[e.jsxs("div",{className:"brand",children:[e.jsx("div",{className:"brand-icon",children:e.jsx("i",{className:"fas fa-sitemap"})}),e.jsxs("div",{className:"brand-text",children:[e.jsx("h2",{children:"Organograma"}),e.jsx("span",{children:"Corporativo"})]})]}),e.jsxs("div",{className:"actions",children:[e.jsxs("div",{className:`search-wrapper ${n?"active":""}`,children:[e.jsx("i",{className:"fas fa-search"}),e.jsx("input",{type:"text",placeholder:"Buscar colaborador...",value:n,onChange:a=>g(a.target.value)}),n&&e.jsx("button",{className:"clear-search",onClick:()=>g(""),children:e.jsx("i",{className:"fas fa-times"})})]}),e.jsxs("div",{className:"zoom-controls",children:[e.jsx("button",{onClick:j,title:"Reduzir Zoom",children:e.jsx("i",{className:"fas fa-minus"})}),e.jsxs("span",{className:"zoom-level",children:[Math.round(i*100),"%"]}),e.jsx("button",{onClick:y,title:"Aumentar Zoom",children:e.jsx("i",{className:"fas fa-plus"})}),e.jsx("div",{className:"separator"}),e.jsx("button",{onClick:E,title:"Resetar",children:e.jsx("i",{className:"fas fa-compress-arrows-alt"})})]}),e.jsxs("a",{href:"/login",className:"btn-login",children:[e.jsx("i",{className:"fas fa-user-circle"})," Login"]})]})]}),e.jsx("main",{className:"canvas",children:e.jsx("div",{className:"tree-wrapper",style:{transform:`scale(${i})`},children:C(r)})}),e.jsx("style",{children:`
                    /* --- Fonts & Vars --- */
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

                    :root {
                        --bg-page: #f8fafc; /* Slate 50 */
                        --bg-card: #ffffff;
                        --text-primary: #0f172a; /* Slate 900 */
                        --text-secondary: #64748b; /* Slate 500 */
                        --border-color: #e2e8f0; /* Slate 200 */
                        --line-color: #cbd5e1; /* Slate 300 */
                        --line-active: #3b82f6; /* Blue 500 */
                        --shadow-sm: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
                        --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -1px rgb(0 0 0 / 0.06);
                        --shadow-hover: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
                        --ease-out: cubic-bezier(0.34, 1.56, 0.64, 1);
                    }

                    * { box-sizing: border-box; }

                    .organogram-page {
                        font-family: 'Inter', sans-serif;
                        background-color: var(--bg-page);
                        height: 100vh;
                        display: flex;
                        flex-direction: column;
                        overflow: hidden;
                        color: var(--text-primary);
                    }

                    /* --- Header --- */
                    .page-header {
                        background: rgba(255, 255, 255, 0.85);
                        backdrop-filter: blur(12px);
                        border-bottom: 1px solid var(--border-color);
                        height: 72px;
                        padding: 0 32px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        z-index: 50;
                        box-shadow: var(--shadow-sm);
                    }

                    .brand {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                    }
                    .brand-icon {
                        width: 36px;
                        height: 36px;
                        background: var(--text-primary);
                        color: #fff;
                        border-radius: 8px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.1rem;
                    }
                    .brand-text h2 {
                        margin: 0;
                        font-size: 1rem;
                        font-weight: 700;
                        letter-spacing: -0.02em;
                        line-height: 1.2;
                    }
                    .brand-text span {
                        font-size: 0.75rem;
                        color: var(--text-secondary);
                        font-weight: 500;
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                    }

                    .actions {
                        display: flex;
                        align-items: center;
                        gap: 24px;
                    }

                    /* Search */
                    .search-wrapper {
                        position: relative;
                        transition: all 0.2s;
                    }
                    .search-wrapper i {
                        position: absolute;
                        left: 12px;
                        top: 50%;
                        transform: translateY(-50%);
                        color: var(--text-secondary);
                        pointer-events: none;
                    }
                    .search-wrapper input {
                        padding: 10px 12px 10px 38px;
                        border: 1px solid var(--border-color);
                        border-radius: 8px;
                        font-size: 0.9rem;
                        width: 260px;
                        background: #fff;
                        color: var(--text-primary);
                        transition: all 0.2s;
                    }
                    .search-wrapper input:focus {
                        outline: none;
                        border-color: #3b82f6;
                        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
                        width: 300px;
                    }
                    .clear-search {
                        position: absolute;
                        right: 8px;
                        top: 50%;
                        transform: translateY(-50%);
                        background: none;
                        border: none;
                        color: var(--text-secondary);
                        cursor: pointer;
                        padding: 4px;
                    }
                    .clear-search:hover { color: var(--text-primary); }

                    /* Zoom */
                    .zoom-controls {
                        display: flex;
                        align-items: center;
                        background: #fff;
                        border: 1px solid var(--border-color);
                        border-radius: 8px;
                        padding: 4px;
                        box-shadow: var(--shadow-sm);
                    }
                    .zoom-controls button {
                        width: 32px;
                        height: 32px;
                        border: none;
                        background: transparent;
                        border-radius: 6px;
                        color: var(--text-secondary);
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.15s;
                    }
                    .zoom-controls button:hover {
                        background: var(--bg-page);
                        color: var(--text-primary);
                    }
                    .zoom-level {
                        font-size: 0.8rem;
                        font-weight: 600;
                        width: 48px;
                        text-align: center;
                        font-variant-numeric: tabular-nums;
                    }
                    .separator {
                        width: 1px;
                        height: 16px;
                        background: var(--border-color);
                        margin: 0 4px;
                    }

                    .btn-login {
                        background: var(--text-primary);
                        color: #fff;
                        text-decoration: none;
                        padding: 10px 16px;
                        border-radius: 8px;
                        font-size: 0.9rem;
                        font-weight: 600;
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        transition: all 0.2s;
                    }
                    .btn-login:hover {
                        background: #334155;
                        transform: translateY(-1px);
                    }

                    /* --- Canvas --- */
                    .canvas {
                        flex: 1;
                        overflow: auto;
                        padding: 80px 40px;
                        cursor: grab;
                        background-image:
                            radial-gradient(#e2e8f0 1px, transparent 1px);
                        background-size: 24px 24px;
                    }
                    .canvas:active { cursor: grabbing; }

                    .tree-wrapper {
                        display: flex;
                        justify-content: center;
                        width: max-content;
                        min-width: 100%;
                        transform-origin: top center;
                        transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
                    }

                    .org-tree {
                        display: flex;
                        justify-content: center;
                        list-style: none;
                        padding: 0;
                        margin: 0;
                        position: relative;
                    }

                    .org-leaf {
                        position: relative;
                        padding: 60px 24px 0 24px; /* Increased spacing */
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                    }

                    /* --- Connectors --- */
                    /* Vertical line from parent */
                    .org-tree::before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 50%;
                        width: 2px;
                        height: 30px;
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                        transition: background-color 0.3s, box-shadow 0.3s;
                    }

                    /* Connectors for children */
                    .org-leaf::before, .org-leaf::after {
                        content: '';
                        position: absolute;
                        top: 0;
                        right: 50%;
                        border-top: 2px solid var(--line-color);
                        width: 50%;
                        height: 30px;
                        transition: border-color 0.3s, box-shadow 0.3s;
                    }
                    .org-leaf::after {
                        right: auto;
                        left: 50%;
                        border-left: 2px solid var(--line-color);
                    }

                    /* Exceptions */
                    .tree-wrapper > .org-tree::before { display: none; }
                    .tree-wrapper > .org-tree > .org-leaf { padding-top: 0; }
                    .org-leaf:only-child::after, .org-leaf:only-child::before { display: none; }
                    .org-leaf:only-child { padding-top: 0; }
                    .org-leaf:first-child::before, .org-leaf:last-child::after { border: 0 none; }

                    /* Corners */
                    .org-leaf:last-child::before {
                        border-right: 2px solid var(--line-color);
                        border-radius: 0 16px 0 0;
                    }
                    .org-leaf:first-child::after {
                        border-radius: 16px 0 0 0;
                    }

                    /* Connector DOWN to children */
                    .org-leaf > ul::before {
                        content: '';
                        position: absolute;
                        top: -30px;
                        left: 50%;
                        width: 2px;
                        height: 30px;
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                        transition: background-color 0.3s, box-shadow 0.3s;
                    }

                    /* --- Active Connection States --- */

                    /* Se a conexão estiver ativa (pai->filho), ilumina as linhas */
                    .org-leaf.conn-active::before,
                    .org-leaf.conn-active::after {
                        border-color: var(--line-active);
                        box-shadow: 0 -1px 4px rgba(59, 130, 246, 0.4);
                        z-index: 1;
                    }

                    /* Linha vertical descendo do pai (renderizada no UL filho anterior)
                       Isso é tricky. No CSS puro é difícil estilizar o "before" do UL baseando no LI pai.
                       Mas podemos estilizar o "before" do UL se tivermos uma classe no UL.
                       Por simplicidade, o 'pulse' vai nas linhas horizontais/verticais do próprio LI.
                    */

                    @keyframes pulse-line {
                        0% { opacity: 0.6; }
                        50% { opacity: 1; box-shadow: 0 0 8px var(--line-active); }
                        100% { opacity: 0.6; }
                    }

                    .org-leaf.conn-active::before,
                    .org-leaf.conn-active::after {
                        animation: pulse-line 2s infinite ease-in-out;
                    }

                    /* --- Card Styles --- */
                    .org-card {
                        background: var(--bg-card);
                        width: 280px;
                        position: relative;
                        border-radius: 12px;
                        box-shadow: var(--shadow-md);
                        transition: all 0.3s var(--ease-out);
                        cursor: pointer;
                        z-index: 2;
                        border: 1px solid rgba(255,255,255,0.1); /* Subtle border for dark mode compatibility if needed */
                        overflow: hidden;
                    }

                    /* Left Accent Bar */
                    .card-accent {
                        height: 4px;
                        width: 100%;
                        background-color: var(--dept-color);
                    }

                    .card-body {
                        padding: 16px;
                        display: flex;
                        flex-direction: column;
                        gap: 12px;
                        background: linear-gradient(180deg, #fff 0%, #fcfcfc 100%);
                    }

                    /* Hover State (The User) */
                    .org-card.state-active {
                        transform: scale(1.05) translateY(-4px);
                        box-shadow: var(--shadow-hover);
                        z-index: 10;
                        border-color: transparent;
                        outline: 2px solid var(--line-active);
                    }

                    /* Subordinate State */
                    .org-card.state-subordinate {
                        transform: translateY(-2px);
                        box-shadow: var(--shadow-md);
                        border-color: var(--line-active);
                        background-color: #f0f9ff; /* Light blue tint */
                    }

                    /* Dimmed State */
                    .org-card.state-dimmed {
                        opacity: 0.4;
                        filter: grayscale(0.8);
                        transform: scale(0.98);
                    }

                    /* Highlight (Search) */
                    .org-card.highlight {
                        background-color: #fffbeb;
                        border: 2px solid #f59e0b;
                    }

                    /* Header Layout */
                    .card-header {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                    }

                    .avatar {
                        width: 44px;
                        height: 44px;
                        border-radius: 10px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: 700;
                        font-size: 1rem;
                        flex-shrink: 0;
                        box-shadow: inset 0 0 0 1px rgba(0,0,0,0.05);
                    }

                    .info {
                        flex: 1;
                        min-width: 0;
                    }

                    .name {
                        margin: 0;
                        font-size: 0.95rem;
                        font-weight: 600;
                        color: var(--text-primary);
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        letter-spacing: -0.01em;
                    }

                    .role {
                        margin: 2px 0 0 0;
                        font-size: 0.8rem;
                        color: var(--text-secondary);
                        display: -webkit-box;
                        -webkit-line-clamp: 2;
                        -webkit-box-orient: vertical;
                        overflow: hidden;
                        line-height: 1.3;
                    }

                    /* Footer */
                    .card-footer {
                        border-top: 1px solid #f1f5f9;
                        padding-top: 10px;
                        display: flex;
                    }

                    .dept-badge {
                        font-size: 0.7rem;
                        font-weight: 600;
                        padding: 2px 8px;
                        border-radius: 99px;
                        border: 1px solid;
                        text-transform: uppercase;
                        letter-spacing: 0.05em;
                        max-width: 100%;
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }

                    /* Toggle Button */
                    .toggle-btn {
                        position: absolute;
                        bottom: -14px;
                        left: 50%;
                        transform: translateX(-50%);
                        width: 28px;
                        height: 28px;
                        background: #fff;
                        border: 1px solid var(--border-color);
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 0.8rem;
                        color: var(--text-secondary);
                        box-shadow: var(--shadow-sm);
                        transition: all 0.2s;
                        z-index: 5;
                    }
                    .toggle-btn:hover {
                        color: var(--text-primary);
                        border-color: var(--text-secondary);
                        transform: translateX(-50%) scale(1.1);
                    }
                    .toggle-btn.expanded i {
                        transform: rotate(180deg);
                        transition: transform 0.3s;
                    }

                    /* Loading / Error */
                    .loading-container, .error-container {
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        height: 100vh;
                        color: var(--text-secondary);
                        gap: 16px;
                    }
                    .spinner {
                        width: 40px;
                        height: 40px;
                        border: 3px solid rgba(0,0,0,0.1);
                        border-radius: 50%;
                        border-top-color: var(--text-primary);
                        animation: spin 0.8s linear infinite;
                    }
                    @keyframes spin { to { transform: rotate(360deg); } }

                `})]})})};$.createRoot(document.getElementById("root")).render(e.jsx(t.StrictMode,{children:e.jsx(D,{})}));
