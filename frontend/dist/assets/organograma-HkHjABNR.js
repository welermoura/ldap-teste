import{a as t,j as e,c as b}from"./index-Q695sD3D.js";const u=()=>{const[d,c]=t.useState([]),[g,i]=t.useState(!0),[n,p]=t.useState(null),[a,h]=t.useState("");t.useEffect(()=>{fetch("/api/public/organogram_data").then(r=>{if(!r.ok)throw new Error("Falha ao carregar dados");return r.json()}).then(r=>{c(r),i(!1)}).catch(r=>{p(r.message),i(!1)})},[]);const l=r=>!r||!Array.isArray(r)||r.length===0?null:e.jsx("ul",{className:"org-tree-ul",children:r.map((o,s)=>{const x=`org-node ${a&&o.name&&o.name.toLowerCase().includes(a.toLowerCase())?"highlight-node":""}`;return e.jsxs("li",{className:"org-tree-li",children:[e.jsxs("div",{className:x,id:`node-${s}`,children:[e.jsx("h6",{children:o.name}),e.jsx("p",{className:"title",children:o.title}),e.jsx("p",{className:"department",children:o.department})]}),o.children&&o.children.length>0&&l(o.children)]},o.distinguishedName||s)})});return g?e.jsx("div",{className:"loading-container",children:"Carregando organograma..."}):n?e.jsxs("div",{className:"error-container",children:["Erro: ",n]}):e.jsxs("div",{className:"organogram-page",children:[e.jsxs("div",{className:"header-container",children:[e.jsxs("h2",{children:[e.jsx("i",{className:"fas fa-sitemap"})," Organograma"]}),e.jsx("div",{className:"search-box",children:e.jsx("input",{type:"text",placeholder:"Buscar colaborador...",value:a,onChange:r=>h(r.target.value),className:"form-control glass-input"})}),e.jsx("a",{href:"/login",className:"btn-login",children:"Login"})]}),e.jsx("div",{className:"organogram-scroll-container",children:e.jsx("div",{className:"org-tree-wrapper",children:l(d)})}),e.jsx("style",{children:`
                .organogram-page {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                    min-height: 100vh;
                    color: white;
                    padding: 20px;
                }
                .header-container {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 30px;
                    background: rgba(255, 255, 255, 0.1);
                    padding: 15px;
                    border-radius: 10px;
                    backdrop-filter: blur(10px);
                }
                .search-box input {
                    background: rgba(255, 255, 255, 0.2);
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    color: white;
                    padding: 8px 15px;
                    border-radius: 20px;
                    outline: none;
                }
                .search-box input::placeholder {
                    color: rgba(255, 255, 255, 0.7);
                }
                .btn-login {
                    color: white;
                    text-decoration: none;
                    border: 1px solid white;
                    padding: 8px 20px;
                    border-radius: 20px;
                    transition: all 0.3s;
                }
                .btn-login:hover {
                    background: white;
                    color: #1e3c72;
                }

                /* Tree CSS */
                .org-tree-wrapper {
                    display: flex;
                    justify-content: center;
                }
                .org-tree-ul {
                    padding-top: 20px;
                    position: relative;
                    transition: all 0.5s;
                    display: flex;
                    justify-content: center;
                }
                .org-tree-li {
                    float: left; text-align: center;
                    list-style-type: none;
                    position: relative;
                    padding: 20px 5px 0 5px;
                    transition: all 0.5s;
                }
                /* Connectors */
                .org-tree-li::before, .org-tree-li::after {
                    content: '';
                    position: absolute; top: 0; right: 50%;
                    border-top: 1px solid #ccc;
                    width: 50%; height: 20px;
                }
                .org-tree-li::after {
                    right: auto; left: 50%;
                    border-left: 1px solid #ccc;
                }
                .org-tree-li:only-child::after, .org-tree-li:only-child::before {
                    display: none;
                }
                .org-tree-li:only-child{ padding-top: 0;}
                .org-tree-li:first-child::before, .org-tree-li:last-child::after{
                    border: 0 none;
                }
                .org-tree-li:last-child::before{
                    border-right: 1px solid #ccc;
                    border-radius: 0 5px 0 0;
                }
                .org-tree-li:first-child::after{
                    border-radius: 5px 0 0 0;
                }
                .org-tree-ul ul::before{
                    content: '';
                    position: absolute; top: 0; left: 50%;
                    border-left: 1px solid #ccc;
                    width: 0; height: 20px;
                }

                .org-node {
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    padding: 10px;
                    text-decoration: none;
                    color: white;
                    font-family: arial, verdana, tahoma;
                    font-size: 11px;
                    display: inline-block;
                    border-radius: 5px;
                    transition: all 0.5s;
                    background: rgba(255, 255, 255, 0.1);
                    backdrop-filter: blur(5px);
                    min-width: 150px;
                }
                .org-node:hover, .org-node:hover+ul li .org-node {
                    background: rgba(255, 255, 255, 0.2);
                    border: 1px solid #94a0b4;
                }
                .org-node:hover+ul li::after,
                .org-node:hover+ul li::before,
                .org-node:hover+ul::before,
                .org-node:hover+ul ul::before{
                    border-color:  #94a0b4;
                }

                .org-node h6 {
                    font-size: 14px;
                    margin: 5px 0;
                    font-weight: bold;
                }
                .org-node .title {
                    font-size: 12px;
                    margin-bottom: 2px;
                }
                .org-node .department {
                    font-size: 10px;
                    opacity: 0.8;
                }

                .highlight-node {
                    border: 2px solid #ffc107 !important;
                    background: rgba(255, 193, 7, 0.3) !important;
                    box-shadow: 0 0 15px rgba(255, 193, 7, 0.5);
                }
            `})]})};b.createRoot(document.getElementById("root")).render(e.jsx(t.StrictMode,{children:e.jsx(u,{})}));
