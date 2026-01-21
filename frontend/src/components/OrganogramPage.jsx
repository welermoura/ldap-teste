import React, { useEffect, useState, useMemo, createContext, useContext, useRef } from 'react';
import {
    ZoomIn,
    ZoomOut,
    RotateCcw,
    UserCircle,
    ChevronDown,
    Network,
    AlertTriangle,
    Loader2,
    Crosshair
} from 'lucide-react';
import OrganogramSearch from './OrganogramSearch';

// --- Context ---
const OrganogramContext = createContext({
    hoveredNodeId: null,
    setHoveredNodeId: () => {},
    selectedNodeId: null,
    setSelectedNodeId: () => {},
    activePath: new Set(),
});

// --- Utility Functions ---

// Generate deterministic color based on department
const getDepartmentColor = (dept) => {
    if (!dept) return '#64748b'; // Slate-500 default

    const palette = {
        'Financeiro': '#059669', // Emerald-600
        'Comercial': '#d97706', // Amber-600
        'Vendas': '#d97706',
        'TI': '#2563eb', // Blue-600
        'Tecnologia': '#2563eb',
        'Recursos Humanos': '#db2777', // Pink-600
        'RH': '#db2777',
        'Diretoria': '#0f172a', // Slate-900
        'Executivo': '#0f172a',
        'Jurídico': '#7c3aed', // Violet-600
        'Marketing': '#ea580c', // Orange-600
        'Operações': '#0891b2', // Cyan-600
    };

    if (palette[dept]) return palette[dept];

    let hash = 0;
    for (let i = 0; i < dept.length; i++) {
        hash = dept.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = Math.abs(hash % 360);
    return `hsl(${hue}, 60%, 40%)`;
};

const getInitials = (name) => {
    if (!name) return '';
    const names = name.split(' ');
    if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
    return name[0].toUpperCase();
};

// --- Components ---

const NodeCard = ({ node, isExpanded, toggleNode, hasChildren, parentId }) => {
    const { hoveredNodeId, setHoveredNodeId, selectedNodeId, setSelectedNodeId, activePath } = useContext(OrganogramContext);
    const deptColor = useMemo(() => getDepartmentColor(node.department), [node.department]);

    const nodeId = node.distinguishedName;

    // States calculation
    const isHovered = hoveredNodeId === nodeId;
    const isSelected = selectedNodeId === nodeId;

    // Highlight logic:
    // 1. If Hovered: Highlight Self + Direct Children + Path to Root
    // 2. If Selected: Highlight Self
    // 3. Otherwise: Dim if something else is hovered

    const isPathRelated = activePath.has(nodeId);
    const isDirectSubordinateOfHover = hoveredNodeId === parentId && hoveredNodeId !== null;

    const isActive = isHovered || isSelected || isDirectSubordinateOfHover || (hoveredNodeId && isPathRelated);
    const isDimmed = hoveredNodeId && !isActive;

    // Executive Check
    const isExecutive = node.title && (
        node.title.toLowerCase().includes('presidente') ||
        node.title.toLowerCase().includes('ceo') ||
        node.title.toLowerCase().includes('diretor')
    );

    const handleMouseEnter = (e) => {
        e.stopPropagation();
        setHoveredNodeId(nodeId);
    };

    const handleMouseLeave = () => {
        setHoveredNodeId(null);
    };

    const handleClick = (e) => {
        e.stopPropagation();
        setSelectedNodeId(nodeId === selectedNodeId ? null : nodeId);
    };

    const handleToggle = (e) => {
        e.stopPropagation();
        if (hasChildren) toggleNode();
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleClick(e);
        }
    };

    return (
        <div
            id={nodeId}
            className={`
                org-card
                ${isExecutive ? 'executive' : ''}
                ${isHovered ? 'state-hover' : ''}
                ${isSelected ? 'state-selected' : ''}
                ${isDimmed ? 'state-dimmed' : ''}
                ${isDirectSubordinateOfHover ? 'state-subordinate' : ''}
            `}
            onClick={handleClick}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onKeyDown={handleKeyDown}
            tabIndex={0}
            role="treeitem"
            aria-label={`${node.name}, ${node.title}, ${node.department}`}
            aria-selected={isSelected}
            aria-expanded={hasChildren ? isExpanded : undefined}
            style={{
                '--dept-color': deptColor,
            }}
        >
            <div className="card-accent"></div>

            <div className="card-body">
                <div className="card-header">
                    <div className="avatar">
                        {getInitials(node.name)}
                    </div>
                    <div className="info">
                        <h6 className="name">{node.name}</h6>
                        <p className="role">{node.title || 'Cargo não definido'}</p>
                    </div>
                </div>

                {node.department && (
                    <div className="card-footer">
                        <span className="dept-badge">
                            {node.department}
                        </span>
                    </div>
                )}
            </div>

            {hasChildren && (
                <button
                    className={`toggle-btn ${isExpanded ? 'expanded' : ''}`}
                    onClick={handleToggle}
                    aria-label={isExpanded ? "Recolher" : "Expandir"}
                    tabIndex={-1} // Focus handled by card
                >
                    <ChevronDown size={14} className="icon-chevron" />
                </button>
            )}
        </div>
    );
};

const OrganogramPage = () => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [zoom, setZoom] = useState(1);
    const [expandedNodes, setExpandedNodes] = useState(new Set());

    // Global State
    const [hoveredNodeId, setHoveredNodeId] = useState(null);
    const [selectedNodeId, setSelectedNodeId] = useState(null);

    // Derived State: Active Path for styling
    const activePath = useMemo(() => {
        const path = new Set();
        const targetId = hoveredNodeId || selectedNodeId;
        if (!targetId || !data.length) return path;

        // Helper to find path to node
        const findPath = (nodes, currentPath = []) => {
            for (const node of nodes) {
                if (node.distinguishedName === targetId) {
                    return [...currentPath, node.distinguishedName];
                }
                if (node.children) {
                    const result = findPath(node.children, [...currentPath, node.distinguishedName]);
                    if (result) return result;
                }
            }
            return null;
        };

        const resultPath = findPath(data);
        if (resultPath) {
            resultPath.forEach(id => path.add(id));
        }
        return path;
    }, [hoveredNodeId, selectedNodeId, data]);

    // Drag-to-pan state
    const canvasRef = useRef(null);
    const [isDragging, setIsDragging] = useState(false);
    const [startPos, setStartPos] = useState({ x: 0, y: 0 });
    const [scrollPos, setScrollPos] = useState({ left: 0, top: 0 });

    useEffect(() => {
        fetch('/api/public/organogram_data')
            .then(res => {
                if (!res.ok) throw new Error('Falha ao carregar dados');
                return res.json();
            })
            .then(data => {
                const validData = Array.isArray(data) ? data : [];
                setData(validData);
                // Initial expansion
                const initialExpanded = new Set();
                validData.forEach((node, index) => {
                    const key = node.distinguishedName || index;
                    initialExpanded.add(key);
                });
                setExpandedNodes(initialExpanded);
                setLoading(false);
            })
            .catch(err => {
                setError(err.message);
                setLoading(false);
            });
    }, []);

    // Scroll handlers
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') setSelectedNodeId(null);
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

    const handleMouseDown = (e) => {
        if (!canvasRef.current) return;
        if (e.target.closest('.org-card') || e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
        setIsDragging(true);
        setStartPos({ x: e.pageX, y: e.pageY });
        setScrollPos({ left: canvasRef.current.scrollLeft, top: canvasRef.current.scrollTop });
    };

    const handleMouseMove = (e) => {
        if (!isDragging || !canvasRef.current) return;
        e.preventDefault();
        const x = e.pageX - startPos.x;
        const y = e.pageY - startPos.y;
        canvasRef.current.scrollLeft = scrollPos.left - x;
        canvasRef.current.scrollTop = scrollPos.top - y;
    };

    const handleMouseUp = () => setIsDragging(false);

    const handleWheel = (e) => {
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            setZoom(prev => Math.min(Math.max(0.3, prev + delta), 2));
        }
    };

    const handleCenterSelection = () => {
        if (selectedNodeId) {
            const el = document.getElementById(selectedNodeId);
            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }
    };

    // Actions
    const handleSelectNode = (nodeId) => {
        // Logic to expand path if coming from search
        // (Simplified here assuming Search component logic works)
        setSelectedNodeId(nodeId);
        setTimeout(() => {
             const el = document.getElementById(nodeId);
             if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
        }, 100);
    };

    const renderTree = (nodes, parentId = null) => {
        if (!nodes || nodes.length === 0) return null;

        return (
            <ul className="org-tree">
                {nodes.map((node) => {
                    const key = node.distinguishedName;
                    const hasChildren = node.children && node.children.length > 0;
                    const isExpanded = expandedNodes.has(key);
                    const isPathActive = (activePath.has(key) && activePath.has(parentId)) || (hoveredNodeId === parentId);

                    // Grid layout logic: If > 8 children, force grid? Or if leaf nodes?
                    // Retaining the 'leaf nodes grid' logic from previous iteration if useful
                    const isLeafGroup = hasChildren && node.children.every(child => !child.children || child.children.length === 0);
                    const isLargeGroup = hasChildren && node.children.length > 8;
                    const useGridLayout = isLeafGroup || isLargeGroup;

                    return (
                        <li key={key} className={`org-leaf ${isPathActive ? 'conn-active' : ''}`}>
                            <NodeCard
                                node={node}
                                isExpanded={isExpanded}
                                toggleNode={() => setExpandedNodes(prev => {
                                    const next = new Set(prev);
                                    if (next.has(key)) next.delete(key);
                                    else next.add(key);
                                    return next;
                                })}
                                hasChildren={hasChildren}
                                parentId={parentId}
                            />
                            {hasChildren && isExpanded && (
                                <div className={useGridLayout ? 'grid-wrapper' : ''}>
                                    {renderTree(node.children, key)}
                                </div>
                            )}
                        </li>
                    );
                })}
            </ul>
        );
    };

    if (loading) return <div className="loading-container"><Loader2 className="spinner" /></div>;
    if (error) return <div className="error-container"><AlertTriangle /> {error}</div>;

    return (
        <OrganogramContext.Provider value={{ hoveredNodeId, setHoveredNodeId, selectedNodeId, setSelectedNodeId, activePath }}>
            <div className="organogram-page">
                <header className="page-header">
                    <div className="brand">
                        <Network size={24} />
                        <div className="brand-text">
                            <h2>Organograma</h2>
                            <span>Corporativo</span>
                        </div>
                    </div>

                    <div className="actions">
                        <OrganogramSearch data={data} onSelect={handleSelectNode} />

                        <div className="toolbar">
                            <button onClick={() => setZoom(z => Math.max(0.3, z - 0.1))} title="Diminuir"><ZoomOut size={18} /></button>
                            <span>{Math.round(zoom * 100)}%</span>
                            <button onClick={() => setZoom(z => Math.min(2, z + 0.1))} title="Aumentar"><ZoomIn size={18} /></button>
                            <div className="sep"></div>
                            <button onClick={() => setZoom(1)} title="Resetar"><RotateCcw size={18} /></button>
                            {selectedNodeId && (
                                <button onClick={handleCenterSelection} title="Centralizar Seleção" className="active-btn">
                                    <Crosshair size={18} />
                                </button>
                            )}
                        </div>

                        <a href="/login" className="btn-login"><UserCircle size={18} /> Login</a>
                    </div>
                </header>

                <main
                    className={`canvas ${isDragging ? 'grabbing' : ''}`}
                    ref={canvasRef}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                    onWheel={handleWheel}
                >
                    <div className="tree-wrapper" style={{ transform: `scale(${zoom})` }}>
                        {renderTree(data)}
                    </div>
                </main>

                <style>{`
                    :root {
                        --bg-page: #f8fafc;
                        --bg-card: #ffffff; /* Off-white handled individually if needed */
                        --text-primary: #0f172a;
                        --text-secondary: #64748b;
                        --border-color: #e2e8f0;
                        --line-color: #cbd5e1;
                        --line-active: #3b82f6;
                        --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                        --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                        --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
                        --shadow-active: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
                    }

                    .organogram-page {
                        font-family: 'Inter', system-ui, sans-serif;
                        background: var(--bg-page);
                        height: 100vh;
                        display: flex;
                        flex-direction: column;
                        overflow: hidden;
                        color: var(--text-primary);
                    }

                    /* Header */
                    .page-header {
                        height: 64px;
                        background: rgba(255,255,255,0.9);
                        backdrop-filter: blur(8px);
                        border-bottom: 1px solid var(--border-color);
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        padding: 0 24px;
                        z-index: 50;
                    }
                    .brand { display: flex; align-items: center; gap: 12px; color: var(--text-primary); }
                    .brand-text h2 { margin: 0; font-size: 1rem; font-weight: 700; line-height: 1.2; }
                    .brand-text span { font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; }

                    .actions { display: flex; align-items: center; gap: 16px; }
                    .toolbar {
                        display: flex;
                        align-items: center;
                        background: #fff;
                        border: 1px solid var(--border-color);
                        border-radius: 8px;
                        padding: 4px;
                        gap: 4px;
                    }
                    .toolbar button {
                        border: none; background: transparent; padding: 6px; border-radius: 4px;
                        color: var(--text-secondary); cursor: pointer; display: flex;
                        transition: all 0.2s;
                    }
                    .toolbar button:hover { background: var(--bg-page); color: var(--text-primary); }
                    .toolbar button.active-btn { color: var(--line-active); background: #eff6ff; }
                    .sep { width: 1px; height: 16px; background: var(--border-color); margin: 0 4px; }

                    .btn-login {
                        text-decoration: none; color: var(--text-primary); font-weight: 600; font-size: 0.9rem;
                        display: flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: 6px;
                        transition: background 0.2s;
                    }
                    .btn-login:hover { background: #e2e8f0; }

                    /* Canvas */
                    .canvas {
                        flex: 1; overflow: hidden; cursor: grab; position: relative;
                        background-image: radial-gradient(#e2e8f0 1px, transparent 1px);
                        background-size: 24px 24px;
                    }
                    .canvas.grabbing { cursor: grabbing; }
                    .tree-wrapper {
                        display: flex; justify-content: center; padding: 80px; min-width: max-content;
                        transform-origin: top center; transition: transform 0.1s linear; /* Fast zoom */
                    }

                    /* Tree Structure */
                    .org-tree { list-style: none; padding: 0; margin: 0; display: flex; justify-content: center; }
                    .org-leaf { position: relative; padding: 40px 16px 0 16px; display: flex; flex-direction: column; align-items: center; }

                    /* Connectors */
                    .org-tree::before, .org-leaf::before, .org-leaf::after, .org-leaf > div::before {
                        content: ''; position: absolute; background: var(--line-color); transition: all 0.3s ease;
                    }
                    .org-tree::before { top: 0; left: 50%; width: 2px; height: 20px; transform: translateX(-50%); }
                    .org-leaf::before, .org-leaf::after { top: 0; right: 50%; width: 50%; height: 20px; border-top: 2px solid var(--line-color); background: transparent; }
                    .org-leaf::after { right: auto; left: 50%; border-left: 2px solid var(--line-color); border-top: none; }
                    .org-leaf:first-child::before, .org-leaf:last-child::after { border: none; }
                    .org-leaf:last-child::before { border-right: 2px solid var(--line-color); border-radius: 0 12px 0 0; }
                    .org-leaf:first-child::after { border-radius: 12px 0 0 0; border-top: 2px solid var(--line-color); }
                    .org-leaf > div::before { top: -20px; left: 50%; width: 2px; height: 20px; transform: translateX(-50%); }

                    /* Hide connectors for root/single */
                    .tree-wrapper > .org-tree::before { display: none; }
                    .org-leaf:only-child::after, .org-leaf:only-child::before { display: none; }
                    .org-leaf:only-child { padding-top: 0; }

                    /* Active Connections */
                    .org-leaf.conn-active::before,
                    .org-leaf.conn-active::after,
                    .org-leaf.conn-active > div::before {
                        border-color: var(--line-active); background-color: var(--line-active);
                        box-shadow: 0 0 6px rgba(59, 130, 246, 0.4);
                        z-index: 1;
                    }

                    /* Grid Layout Override */
                    .grid-wrapper { display: flex; justify-content: center; position: relative; padding-top: 20px; }
                    .grid-wrapper::before { content: ''; position: absolute; top: 0; left: 50%; width: 2px; height: 20px; background: var(--line-color); transform: translateX(-50%); }
                    .grid-wrapper > .org-tree {
                        display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
                    }
                    .grid-wrapper > .org-tree::before { display: none; }
                    .grid-wrapper .org-leaf { padding: 0; }
                    .grid-wrapper .org-leaf::before, .grid-wrapper .org-leaf::after { display: none; }

                    /* Card Design */
                    .org-card {
                        background: #FAFAFB; /* Off-white */
                        width: 260px;
                        border-radius: 12px;
                        box-shadow: var(--shadow-md);
                        position: relative;
                        transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
                        cursor: pointer;
                        overflow: hidden;
                        border: 1px solid transparent;
                        z-index: 2;
                    }
                    .card-accent { height: 4px; width: 100%; background: var(--dept-color); }
                    .card-body { padding: 16px; display: flex; flex-direction: column; gap: 8px; }

                    .card-header { display: flex; gap: 12px; align-items: center; }
                    .avatar {
                        width: 40px; height: 40px; border-radius: 10px;
                        background: #fff; color: var(--dept-color);
                        display: flex; align-items: center; justify-content: center;
                        font-weight: 700; font-size: 1rem;
                        box-shadow: var(--shadow-sm); border: 1px solid var(--border-color);
                    }
                    .info { flex: 1; min-width: 0; }
                    .name { margin: 0; font-weight: 700; font-size: 0.95rem; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                    .role { margin: 0; font-size: 0.8rem; color: var(--text-secondary); line-height: 1.3; }
                    .dept-badge {
                        display: inline-block; padding: 2px 8px; border-radius: 4px;
                        font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
                        background: rgba(0,0,0,0.03); color: var(--dept-color);
                    }

                    /* States */
                    .org-card.state-hover {
                        transform: translateY(-4px) scale(1.02);
                        box-shadow: var(--shadow-active);
                        z-index: 10;
                        border-color: rgba(0,0,0,0.1);
                    }
                    .org-card.state-selected {
                        border: 2px solid var(--line-active);
                        transform: translateY(-2px);
                        box-shadow: var(--shadow-active);
                        z-index: 20;
                        background: #fff;
                    }
                    .org-card.state-dimmed {
                        opacity: 0.5; filter: grayscale(0.8);
                    }
                    .org-card.executive { border-left: 4px solid var(--text-primary); }

                    /* Toggle Button */
                    .toggle-btn {
                        position: absolute; bottom: -12px; left: 50%; transform: translateX(-50%);
                        width: 24px; height: 24px; border-radius: 50%;
                        background: #fff; border: 1px solid var(--border-color);
                        color: var(--text-secondary); cursor: pointer;
                        display: flex; align-items: center; justify-content: center;
                        transition: all 0.2s; box-shadow: var(--shadow-sm); z-index: 5;
                    }
                    .toggle-btn:hover { color: var(--line-active); border-color: var(--line-active); transform: translateX(-50%) scale(1.1); }
                    .toggle-btn.expanded .icon-chevron { transform: rotate(180deg); }

                    /* Loading */
                    .loading-container { height: 100vh; display: flex; align-items: center; justify-content: center; }
                    .spinner { animation: spin 1s linear infinite; color: var(--line-active); }
                    @keyframes spin { to { transform: rotate(360deg); } }
                `}</style>
            </div>
        </OrganogramContext.Provider>
    );
};

export default OrganogramPage;
