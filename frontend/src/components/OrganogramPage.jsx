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
    LocateFixed
} from 'lucide-react';
import OrganogramSearch from './OrganogramSearch';

// --- Context ---
const OrganogramContext = createContext({
    hoveredNodeId: null,
    setHoveredNodeId: () => {},
    focusedNodeId: null,
    setFocusedNodeId: () => {},
    ancestorIds: new Set(),
});

// --- Utility Functions ---

const getDepartmentColor = (dept) => {
    if (!dept) return '#64748b'; // Slate-500 default

    const palette = {
        'Financeiro': '#059669', // Emerald
        'Comercial': '#d97706', // Amber
        'Vendas': '#d97706',
        'TI': '#2563eb', // Blue
        'Tecnologia': '#2563eb',
        'Recursos Humanos': '#db2777', // Pink
        'RH': '#db2777',
        'Diretoria': '#0f172a', // Slate-900
        'Executivo': '#0f172a',
        'Jurídico': '#7c3aed', // Violet
        'Marketing': '#ea580c', // Orange
        'Operações': '#0891b2', // Cyan
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

const NodeCard = ({ node, isExpanded, toggleNode, hasChildren, isMatch, parentId }) => {
    const { hoveredNodeId, setHoveredNodeId, focusedNodeId, setFocusedNodeId, ancestorIds } = useContext(OrganogramContext);
    const deptColor = useMemo(() => getDepartmentColor(node.department), [node.department]);

    const nodeId = node.distinguishedName;

    // States calculation
    const isHovered = hoveredNodeId === nodeId;
    const isFocused = focusedNodeId === nodeId;
    const isDirectSubordinate = hoveredNodeId === parentId && hoveredNodeId !== null;
    const isAncestor = ancestorIds.has(nodeId);

    // Logic: Dim if someone is focused/hovered, but this node is NOT involved
    // Involved = Hovered OR Focused OR Direct Subordinate OR Ancestor
    const isInteracting = hoveredNodeId !== null || focusedNodeId !== null;
    const isRelevant = isHovered || isFocused || isDirectSubordinate || isAncestor;
    const isDimmed = isInteracting && !isRelevant;

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

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setFocusedNodeId(nodeId);
            if (hasChildren) toggleNode();
        }
    };

    return (
        <div
            id={nodeId}
            className={`
                org-card
                ${isMatch ? 'highlight' : ''}
                ${isExecutive ? 'executive' : ''}
                ${isHovered ? 'state-active' : ''}
                ${isFocused ? 'state-focused' : ''}
                ${isDirectSubordinate ? 'state-subordinate' : ''}
                ${isAncestor ? 'state-ancestor' : ''}
                ${isDimmed ? 'state-dimmed' : ''}
            `}
            onClick={(e) => {
                e.stopPropagation();
                setFocusedNodeId(nodeId);
                if (hasChildren) toggleNode();
            }}
            onKeyDown={handleKeyDown}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            style={{
                '--dept-color': deptColor,
            }}
            role="button"
            aria-expanded={isExpanded}
            aria-label={`${node.name}, ${node.title}`}
            tabIndex={0}
        >
            <div className="card-accent"></div>

            <div className="card-body">
                <div className="card-header">
                    <div className="avatar" style={{
                        backgroundColor: isExecutive ? '#0f172a' : `${deptColor}10`,
                        color: isExecutive ? '#fff' : deptColor
                    }}>
                        {getInitials(node.name)}
                    </div>
                    <div className="info">
                        <h6 className="name" title={node.name}>{node.name}</h6>
                        <p className="role" title={node.title}>{node.title || 'Cargo não definido'}</p>
                    </div>
                </div>

                {node.department && (
                    <div className="card-footer">
                        <span className="dept-badge" style={{
                             backgroundColor: `${deptColor}08`,
                             color: deptColor,
                             borderColor: `${deptColor}20`
                        }}>
                            {node.department}
                        </span>
                    </div>
                )}
            </div>

            {hasChildren && (
                <div className={`toggle-btn ${isExpanded ? 'expanded' : ''}`}>
                    <ChevronDown size={14} className="icon-chevron" />
                </div>
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
    const [expandedGroups, setExpandedGroups] = useState(new Set()); // For "+N others"
    const [hoveredNodeId, setHoveredNodeId] = useState(null);
    const [focusedNodeId, setFocusedNodeId] = useState(null);
    const [ancestorIds, setAncestorIds] = useState(new Set());

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

                // Expandir raízes inicialmente
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

    // Helper: Find Path
    const findPathToNode = (nodes, targetId, path = []) => {
        for (const node of nodes) {
            const currentId = node.distinguishedName;
            if (currentId === targetId) {
                return [...path, currentId]; // Include target for full highlighting
            }
            if (node.children) {
                const result = findPathToNode(node.children, targetId, [...path, currentId]);
                if (result) return result;
            }
        }
        return null;
    };

    // Update Ancestors on Hover/Focus
    useEffect(() => {
        const targetId = hoveredNodeId || focusedNodeId;
        if (targetId) {
            const path = findPathToNode(data, targetId);
            if (path) {
                setAncestorIds(new Set(path));
            } else {
                setAncestorIds(new Set());
            }
        } else {
            setAncestorIds(new Set());
        }
    }, [hoveredNodeId, focusedNodeId, data]);

    // Zoom on Wheel
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        const handleWheel = (e) => {
            if (e.ctrlKey || e.metaKey || true) { // Default behavior for canvas zoom
                e.preventDefault();
                const delta = -e.deltaY * 0.001;
                setZoom(prev => Math.min(Math.max(prev + delta, 0.4), 2));
            }
        };

        canvas.addEventListener('wheel', handleWheel, { passive: false });
        return () => canvas.removeEventListener('wheel', handleWheel);
    }, []);

    // Scroll effect for focused node
    useEffect(() => {
        if (focusedNodeId) {
            setTimeout(() => {
                const element = document.getElementById(focusedNodeId);
                if (element) {
                    element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
                }
            }, 100);

            const timer = setTimeout(() => {
                setFocusedNodeId(null);
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [focusedNodeId]);

    // Drag handlers
    const handleMouseDown = (e) => {
        if (!canvasRef.current) return;
        setIsDragging(true);
        setStartPos({ x: e.pageX, y: e.pageY });
        setScrollPos({
            left: canvasRef.current.scrollLeft,
            top: canvasRef.current.scrollTop
        });
    };

    const handleMouseMove = (e) => {
        if (!isDragging || !canvasRef.current) return;
        e.preventDefault();
        const x = e.pageX - startPos.x;
        const y = e.pageY - startPos.y;
        canvasRef.current.scrollLeft = scrollPos.left - x;
        canvasRef.current.scrollTop = scrollPos.top - y;
    };

    const handleMouseUp = () => {
        setIsDragging(false);
    };

    const toggleNode = (key) => {
        setExpandedNodes(prev => {
            const newSet = new Set(prev);
            if (newSet.has(key)) {
                newSet.delete(key);
            } else {
                newSet.add(key);
            }
            return newSet;
        });
    };

    const handleSelectNode = (nodeId) => {
        const path = findPathToNode(data, nodeId);
        if (path) {
            setExpandedNodes(prev => new Set([...prev, ...path]));
        }
        setFocusedNodeId(nodeId);
    };

    const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.1, 2));
    const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.1, 0.4));
    const handleResetZoom = () => setZoom(1);

    const handleCenterFocused = () => {
        if (focusedNodeId) {
            const element = document.getElementById(focusedNodeId);
            if (element) {
                element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
            }
        }
    };

    // Recursively render tree
    const renderTree = (nodes, parentId = null, parentKey = null) => {
        if (!nodes || !Array.isArray(nodes) || nodes.length === 0) return null;

        const GROUP_LIMIT = 8;
        const isGroupExpanded = parentKey && expandedGroups.has(parentKey);
        const shouldGroup = nodes.length > GROUP_LIMIT && !isGroupExpanded;

        const displayNodes = shouldGroup ? nodes.slice(0, GROUP_LIMIT) : nodes;
        const remainingCount = nodes.length - GROUP_LIMIT;

        // Determine target for path logic
        const targetId = hoveredNodeId || focusedNodeId;

        return (
            <ul className="org-tree">
                {displayNodes.map((node, index) => {
                    const key = node.distinguishedName || index;
                    const hasChildren = node.children && node.children.length > 0;
                    const isExpanded = expandedNodes.has(key);

                    // Connection State Logic
                    const isPathActive = (ancestorIds.has(parentId) && ancestorIds.has(key)) ||
                                         (hoveredNodeId === parentId);

                    // Downward Connection Logic (Pass-through ancestor)
                    // If this node is in the ancestor path AND is NOT the final target,
                    // it means the path flows through it to a child.
                    const isPassThrough = ancestorIds.has(key) && key !== targetId;

                    return (
                        <li key={key} className={`org-leaf ${isPathActive ? 'conn-active' : ''} ${isPassThrough ? 'conn-descendant' : ''}`}>
                            <NodeCard
                                node={node}
                                isExpanded={isExpanded}
                                toggleNode={() => toggleNode(key)}
                                hasChildren={hasChildren}
                                isMatch={false}
                                parentId={parentId}
                            />
                            {hasChildren && isExpanded && renderTree(node.children, key, key)}
                        </li>
                    );
                })}

                {shouldGroup && (
                    <li className="org-leaf">
                         <div
                            className="org-card group-node"
                            onClick={() => setExpandedGroups(prev => new Set([...prev, parentKey]))}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    setExpandedGroups(prev => new Set([...prev, parentKey]));
                                }
                            }}
                            role="button"
                            tabIndex={0}
                            title="Expandir todos"
                         >
                            <div className="card-body" style={{ alignItems: 'center', justifyContent: 'center', padding: '12px' }}>
                                <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                                    +{remainingCount} Colaboradores
                                </span>
                                <ChevronDown size={16} color="var(--text-secondary)" />
                            </div>
                         </div>
                    </li>
                )}
            </ul>
        );
    };

    if (loading) return (
        <div className="loading-container">
            <Loader2 className="spinner" size={40} />
            <p>Carregando estrutura...</p>
        </div>
    );

    if (error) return (
        <div className="error-container">
            <AlertTriangle size={48} className="text-red-500" />
            <p>Erro ao carregar: {error}</p>
        </div>
    );

    return (
        <OrganogramContext.Provider value={{ hoveredNodeId, setHoveredNodeId, focusedNodeId, setFocusedNodeId, ancestorIds }}>
            <div className="organogram-page">
                <header className="page-header">
                    <div className="brand">
                        <div className="brand-icon">
                            <Network size={20} />
                        </div>
                        <div className="brand-text">
                            <h2>Organograma</h2>
                            <span>Corporativo</span>
                        </div>
                    </div>

                    <div className="actions">
                        <OrganogramSearch data={data} onSelect={handleSelectNode} />

                        <div className="zoom-controls">
                            <button onClick={handleCenterFocused} disabled={!focusedNodeId} title="Centralizar Seleção" style={{ opacity: focusedNodeId ? 1 : 0.4 }}>
                                <LocateFixed size={16} />
                            </button>
                            <div className="separator"></div>
                            <button onClick={handleZoomOut} title="Reduzir Zoom"><ZoomOut size={16} /></button>
                            <span className="zoom-level">{Math.round(zoom * 100)}%</span>
                            <button onClick={handleZoomIn} title="Aumentar Zoom"><ZoomIn size={16} /></button>
                            <div className="separator"></div>
                            <button onClick={handleResetZoom} title="Resetar"><RotateCcw size={14} /></button>
                        </div>

                        <a href="/login" className="btn-login">
                            <UserCircle size={18} /> Login
                        </a>
                    </div>
                </header>

                <main
                    className={`canvas ${isDragging ? 'grabbing' : ''}`}
                    ref={canvasRef}
                    onMouseDown={handleMouseDown}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                >
                    <div
                        className="tree-wrapper"
                        style={{
                            transform: `scale(${zoom})`,
                        }}
                    >
                        {renderTree(data)}
                    </div>
                </main>

                <style>{`
                    /* --- Fonts & Vars --- */
                    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

                    :root {
                        --bg-page: #f8fafc; /* Slate 50 */
                        --bg-card: #FAFAFB; /* Off-white premium */
                        --text-primary: #1e293b; /* Slate 800 */
                        --text-secondary: #64748b; /* Slate 500 */
                        --border-color: #e2e8f0; /* Slate 200 */
                        --line-color: #cbd5e1; /* Slate 300 */
                        --line-active: #3b82f6; /* Blue 500 */

                        /* Shadows - Premium Depth */
                        --shadow-sm: 0 2px 4px rgba(0,0,0,0.02), 0 1px 2px rgba(0,0,0,0.03);
                        --shadow-md: 0 8px 16px -4px rgba(0,0,0,0.04), 0 4px 8px -2px rgba(0,0,0,0.02);
                        --shadow-hover: 0 20px 30px -8px rgba(0,0,0,0.08), 0 8px 12px -4px rgba(0,0,0,0.03);

                        --ease-out: cubic-bezier(0.25, 0.46, 0.45, 0.94);
                        --ease-elastic: cubic-bezier(0.34, 1.56, 0.64, 1);
                    }

                    * { box-sizing: border-box; }

                    .organogram-page {
                        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
                        user-select: none; /* Prevent text selection while dragging */
                    }
                    .canvas:active { cursor: grabbing; }
                    .canvas.grabbing { cursor: grabbing; }

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
                        padding: 60px 32px 0 32px; /* Increased horizontal spacing to prevent overlap */
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
                        transition: all 0.2s var(--ease-out);
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
                        transition: all 0.2s var(--ease-out);
                    }
                    .org-leaf::after {
                        right: auto;
                        left: 50%;
                        border-left: 2px solid var(--line-color);
                    }

                    /* Exceptions */
                    .tree-wrapper > .org-tree::before { display: none; }
                    .tree-wrapper > .org-tree > .org-leaf { padding-top: 0; }
                    /* Ensure vertical connector remains for only-child, just hide horizontal arms */
                    .org-leaf:only-child::after { display: none; }
                    .org-leaf:only-child::before { display: none; }
                    /* But we need a vertical line for only-child if padding exists */
                    /* Actually, standard tree usually relies on the parent's UL having a line down.
                       If we keep padding-top: 60px, we need a line to bridge it.
                       Let's add a specific connector for only-child */
                    .org-leaf:only-child { padding-top: 60px; }
                    .org-leaf:only-child > .org-card::before {
                        content: '';
                        position: absolute;
                        top: -30px; /* Bridge the gap from the parent's line */
                        left: 50%;
                        width: 2px;
                        height: 30px;
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                    }

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
                        transition: all 0.2s var(--ease-out);
                    }

                    /* --- Active Connection States --- */

                    /* Se a conexão estiver ativa (pai->filho), ilumina as linhas */
                    .org-leaf.conn-active::before,
                    .org-leaf.conn-active::after {
                        border-color: var(--line-active);
                        /* Remove shadows/filters to prevent "ghost box" artifacts */
                        box-shadow: none;
                        filter: none;
                        z-index: 1;
                        pointer-events: none;
                    }

                    /* Pulse Animation (Opacity only) */
                    @keyframes pulse-line {
                        0% { opacity: 0.5; }
                        50% { opacity: 1; }
                        100% { opacity: 0.5; }
                    }

                    .org-leaf.conn-active::before,
                    .org-leaf.conn-active::after {
                        animation: pulse-line 2s infinite ease-in-out;
                    }

                    /* Prevent active state from highlighting outer arms */
                    .org-leaf:first-child.conn-active::before { border-color: transparent; }
                    .org-leaf:last-child.conn-active::after { border-color: transparent; }

                    /* Highlight downward line for pass-through ancestors */
                    .org-leaf.conn-descendant > ul::before {
                        background-color: var(--line-active);
                    }

                    /* Highlight vertical connector for only-child */
                    .org-leaf:only-child.conn-active > .org-card::before {
                        background-color: var(--line-active);
                    }

                    /* --- Card Styles --- */
                    .org-card {
                        background: var(--bg-card);
                        width: 280px;
                        position: relative;
                        border-radius: 12px;
                        box-shadow: var(--shadow-md);
                        transition: all 0.2s var(--ease-out);
                        cursor: pointer;
                        z-index: 2;
                        border: 1px solid transparent;
                        display: flex;
                        flex-direction: row;
                        outline: none; /* Remove native focus ring, we use custom */
                    }

                    /* Left Accent Bar (Vertical now, as requested "barra lateral colorida") */
                    .card-accent {
                        width: 5px;
                        height: 100%;
                        background-color: var(--dept-color);
                        flex-shrink: 0;
                    }

                    .card-body {
                        flex: 1;
                        padding: 14px 16px;
                        display: flex;
                        flex-direction: column;
                        gap: 10px;
                        /* Background handled by parent .org-card */
                        border-radius: 0 12px 12px 0;
                    }

                    /* Hover State */
                    .org-card.state-active {
                        transform: scale(1.03);
                        box-shadow: var(--shadow-hover);
                        z-index: 50;
                        border-color: var(--line-active);
                    }

                    /* Focused State */
                    .org-card.state-focused {
                        transform: scale(1.03);
                        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3), var(--shadow-hover);
                        border-color: var(--line-active);
                        z-index: 50;
                    }

                    /* Subordinate State */
                    .org-card.state-subordinate {
                        transform: translateY(-2px);
                        box-shadow: var(--shadow-md);
                        background-color: #fff;
                        border: 1px solid var(--line-active);
                    }

                    /* Ancestor State */
                    .org-card.state-ancestor {
                         /* No border to avoid "ghost box" effect */
                         box-shadow: var(--shadow-md);
                    }

                    /* Dimmed State */
                    .org-card.state-dimmed {
                        opacity: 0.55;
                        filter: grayscale(0.6);
                        transform: scale(0.98);
                    }

                    /* Highlight (Search Match) */
                    .org-card.highlight {
                        background-color: #fffbeb;
                        border: 1px solid #f59e0b;
                    }

                    /* Header Layout */
                    .card-header {
                        display: flex;
                        align-items: center;
                        gap: 14px;
                    }

                    .avatar {
                        width: 42px;
                        height: 42px;
                        border-radius: 50%; /* Circular for modern look */
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
                        font-size: 1rem;
                        font-weight: 700;
                        color: var(--text-primary);
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        letter-spacing: -0.015em;
                        line-height: 1.2;
                    }

                    .role {
                        margin: 3px 0 0 0;
                        font-size: 0.85rem;
                        color: var(--text-secondary);
                        font-weight: 500;
                        display: -webkit-box;
                        -webkit-line-clamp: 2;
                        -webkit-box-orient: vertical;
                        overflow: hidden;
                        line-height: 1.35;
                    }

                    /* Footer */
                    .card-footer {
                        padding-top: 4px;
                        display: flex;
                    }

                    .dept-badge {
                        font-size: 0.7rem;
                        font-weight: 600;
                        padding: 3px 10px;
                        border-radius: 6px;
                        border: 1px solid;
                        text-transform: uppercase;
                        letter-spacing: 0.04em;
                        max-width: 100%;
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        background-color: transparent; /* Overridden inline */
                    }

                    /* Group Node */
                    .group-node {
                        height: 60px;
                        border: 1px dashed var(--line-color);
                        background: rgba(255,255,255,0.5);
                    }
                    .group-node:hover {
                        border-color: var(--line-active);
                        background: #fff;
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
                    .toggle-btn.expanded .icon-chevron {
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
                        color: var(--text-primary);
                        animation: spin 1s linear infinite;
                    }
                    @keyframes spin { to { transform: rotate(360deg); } }

                `}</style>
            </div>
        </OrganogramContext.Provider>
    );
};

export default OrganogramPage;
