import{a as t,j as e,c as b}from"./index-Q695sD3D.js";const m=()=>{const[d,c]=t.useState([]),[p,i]=t.useState(!0),[n,g]=t.useState(null),[a,h]=t.useState("");t.useEffect(()=>{fetch("/api/public/organogram_data").then(r=>{if(!r.ok)throw new Error("Falha ao carregar dados");return r.json()}).then(r=>{c(Array.isArray(r)?r:[]),i(!1)}).catch(r=>{g(r.message),i(!1)})},[]);const x=r=>{if(!r)return"";const o=r.split(" ");return o.length>=2?`${o[0][0]}${o[o.length-1][0]}`.toUpperCase():r[0].toUpperCase()},s=r=>!r||!Array.isArray(r)||r.length===0?null:e.jsx("ul",{className:"org-tree-ul",children:r.map((o,l)=>{const f=`org-node ${a&&o.name&&o.name.toLowerCase().includes(a.toLowerCase())?"highlight-node":""}`;return e.jsxs("li",{className:"org-tree-li",children:[e.jsxs("div",{className:f,id:`node-${l}`,children:[e.jsx("div",{className:"avatar",children:x(o.name)}),e.jsxs("div",{className:"node-content",children:[e.jsx("h6",{children:o.name}),e.jsx("p",{className:"title",children:o.title}),e.jsx("p",{className:"department",children:o.department})]})]}),o.children&&o.children.length>0&&s(o.children)]},o.distinguishedName||l)})});return p?e.jsxs("div",{className:"loading-container",children:[e.jsx("div",{className:"spinner"})," Carregando organograma..."]}):n?e.jsxs("div",{className:"error-container",children:["Erro: ",n]}):e.jsxs("div",{className:"organogram-page",children:[e.jsxs("div",{className:"header-container",children:[e.jsxs("h2",{children:[e.jsx("i",{className:"fas fa-sitemap"})," Organograma"]}),e.jsx("div",{className:"search-box",children:e.jsx("input",{type:"text",placeholder:"Buscar colaborador...",value:a,onChange:r=>h(r.target.value),className:"form-control glass-input"})}),e.jsx("a",{href:"/login",className:"btn-login",children:"Login"})]}),e.jsx("div",{className:"organogram-scroll-container",children:e.jsx("div",{className:"org-tree-wrapper",children:s(d)})}),e.jsx("style",{children:`
                .organogram-page {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #f0f2f5 0%, #e1e5ea 100%);
                    min-height: 100vh;
                    color: #333;
                    padding: 20px;
                }
                .header-container {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 30px;
                    background: white;
                    padding: 15px 30px;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                }
                .header-container h2 {
                    margin: 0;
                    font-size: 1.5rem;
                    color: #2c3e50;
                }
                .search-box input {
                    background: #f8f9fa;
                    border: 1px solid #dee2e6;
                    color: #495057;
                    padding: 10px 20px;
                    border-radius: 20px;
                    outline: none;
                    width: 300px;
                    transition: border-color 0.3s;
                }
                .search-box input:focus {
                    border-color: #007bff;
                }
                .btn-login {
                    color: #007bff;
                    text-decoration: none;
                    border: 1px solid #007bff;
                    padding: 8px 25px;
                    border-radius: 20px;
                    transition: all 0.3s;
                    font-weight: 600;
                }
                .btn-login:hover {
                    background: #007bff;
                    color: white;
                }

                .loading-container, .error-container {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    font-size: 1.2rem;
                    color: #6c757d;
                }

                /* Tree CSS - Org Explorer Style */
                .organogram-scroll-container {
                    overflow: auto;
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    min-height: 80vh;
                }

                .org-tree-wrapper {
                    display: flex;
                    justify-content: center;
                    min-width: max-content;
                }
                .org-tree-ul {
                    padding-top: 20px;
                    position: relative;
                    transition: all 0.5s;
                    display: flex;
                    justify-content: center;
                    margin: 0;
                    padding-left: 0;
                }
                .org-tree-li {
                    float: left; text-align: center;
                    list-style-type: none;
                    position: relative;
                    padding: 20px 10px 0 10px;
                    transition: all 0.5s;
                }
                /* Connectors */
                .org-tree-li::before, .org-tree-li::after {
                    content: '';
                    position: absolute; top: 0; right: 50%;
                    border-top: 2px solid #ccc;
                    width: 50%; height: 20px;
                }
                .org-tree-li::after {
                    right: auto; left: 50%;
                    border-left: 2px solid #ccc;
                }
                .org-tree-li:only-child::after, .org-tree-li:only-child::before {
                    display: none;
                }
                .org-tree-li:only-child{ padding-top: 0;}
                .org-tree-li:first-child::before, .org-tree-li:last-child::after{
                    border: 0 none;
                }
                .org-tree-li:last-child::before{
                    border-right: 2px solid #ccc;
                    border-radius: 0 5px 0 0;
                }
                .org-tree-li:first-child::after{
                    border-radius: 5px 0 0 0;
                }
                .org-tree-ul ul::before{
                    content: '';
                    position: absolute; top: 0; left: 50%;
                    border-left: 2px solid #ccc;
                    width: 0; height: 20px;
                }

                /* Node Card */
                .org-node {
                    border: 1px solid #e0e0e0;
                    padding: 15px;
                    text-decoration: none;
                    color: #333;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 13px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    border-radius: 8px;
                    transition: all 0.3s;
                    background: #fff;
                    width: 180px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                    z-index: 1;
                    position: relative;
                }
                .org-node:hover {
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    transform: translateY(-3px);
                    border-color: #007bff;
                }

                .avatar {
                    width: 50px;
                    height: 50px;
                    background: #e9ecef;
                    color: #495057;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    font-size: 18px;
                    margin-bottom: 10px;
                    border: 2px solid white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }

                .node-content h6 {
                    font-size: 14px;
                    margin: 0 0 5px 0;
                    font-weight: 700;
                    color: #212529;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 150px;
                }
                .org-node .title {
                    font-size: 12px;
                    margin-bottom: 3px;
                    color: #6c757d;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    max-width: 150px;
                }
                .org-node .department {
                    font-size: 11px;
                    color: #adb5bd;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }

                .highlight-node {
                    border: 2px solid #ffc107 !important;
                    background: #fff9e6 !important;
                    box-shadow: 0 0 15px rgba(255, 193, 7, 0.5);
                }

                /* Connectors hover effect */
                .org-node:hover+ul li::after,
                .org-node:hover+ul li::before,
                .org-node:hover+ul::before,
                .org-node:hover+ul ul::before{
                    border-color: #007bff;
                }
            `})]})};b.createRoot(document.getElementById("root")).render(e.jsx(t.StrictMode,{children:e.jsx(m,{})}));
