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
    LocateFixed,
    CheckCircle2,
    Clock,
    XCircle,
    Mail,
    Phone,
    MapPin,
    ChevronRight,
    ChevronsDown,
    ChevronsUp
} from 'lucide-react';
import OrganogramSearch from './OrganogramSearch';

// --- Context ---
const OrganogramContext = createContext({
    hoveredNodeId: null,
    setHoveredNodeId: () => {},
    focusedNodeId: null,
    setFocusedNodeId: () => {},
    ancestorIds: new Set(),
    setTooltipData: () => {},
});

// --- Utility Functions ---

const NODE_COLORS = [
    '#059669', // Emerald
    '#d97706', // Amber
    '#2563eb', // Blue
    '#db2777', // Pink
    '#7c3aed', // Violet
    '#ea580c', // Orange
    '#0891b2', // Cyan
    '#4f46e5', // Indigo
    '#dc2626', // Red
    '#65a30d', // Lime
];

const getNodeColor = (index) => {
    return NODE_COLORS[index % NODE_COLORS.length];
};

const getInitials = (name) => {
    if (!name) return '';
    const names = name.split(' ');
    if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
    return name[0].toUpperCase();
};

// --- Components ---

const ActiveConnector = ({ data, hoveredNodeId, focusedNodeId, ancestorIds, zoom }) => {
    const [path, setPath] = useState('');
    const containerRef = useRef(null);

    useEffect(() => {
        const updatePath = () => {
            const activeId = hoveredNodeId || focusedNodeId;
            if (!activeId) {
                setPath('');
                return;
            }

            // Map of DN -> Parent DN
            const parentMap = new Map();
            // Set of IDs that are inside an aggregate group
            const aggregatedNodeSet = new Set();

            const traverse = (nodes, parentId = null) => {
                const GRID_THRESHOLD = 3;
                const leafNodes = [];
                nodes.forEach(node => {
                    if (parentId) parentMap.set(node.distinguishedName, parentId);

                    if (!node.children || node.children.length === 0) {
                        leafNodes.push(node);
                    } else {
                         traverse(node.children, node.distinguishedName);
                    }
                });

                // Mimic aggregation logic
                if (nodes.length > GRID_THRESHOLD && leafNodes.length > 0) {
                     leafNodes.forEach(n => aggregatedNodeSet.add(n.distinguishedName));
                }
            };
            traverse(data);

            const paths = [];

            let currentId = activeId;
            let parentId = parentMap.get(currentId);

            // Special handling: if the ACTIVE node itself is aggregated, start drawing from the Box, not the node.
            // This prevents the line from penetrating the box to find the specific card.
            // We do this by swapping currentId to the aggregate box ID effectively.
            // But we need to handle this in the loop.

            while (parentId) {
                let childEl;
                let isAggregated = aggregatedNodeSet.has(currentId);

                if (isAggregated) {
                     // If aggregated, the connector should come from the Aggregate Box Top
                     childEl = document.getElementById(`aggregate-${parentId}`);
                } else {
                     childEl = document.getElementById(currentId);
                     // If not found (e.g. collapsed branch?), try finding aggregate box just in case logic mismatch
                     if (!childEl) {
                         const aggId = `aggregate-${parentId}`;
                         childEl = document.getElementById(aggId);
                     }
                }

                const parentEl = document.getElementById(parentId);

                if (childEl && parentEl) {
                    const childRect = childEl.getBoundingClientRect();
                    const parentRect = parentEl.getBoundingClientRect();

                    const startX = childRect.left + childRect.width / 2;
                    const startY = childRect.top; // Top of Child (or Box)
                    const endX = parentRect.left + parentRect.width / 2;
                    const endY = parentRect.bottom; // Bottom of Parent

                    const midY = (startY + endY) / 2;

                    const d = `M ${startX} ${startY} V ${midY} H ${endX} V ${endY}`;
                    paths.push(d);
                }

                // If we were aggregated, we just drew line Parent -> Box.
                // We do NOT draw a line inside the box.
                // The loop continues upwards.

                currentId = parentId;
                parentId = parentMap.get(currentId);
            }

            setPath(paths.join(' '));
        };

        // Update on mount, hover change, and window resize/scroll
        updatePath();
        window.addEventListener('resize', updatePath);
        window.addEventListener('scroll', updatePath, true); // Capture scroll

        // Also need to update when expansion changes (layout shift)
        // We can use a MutationObserver or just polling/timeout?
        // Since React handles expansion, a useEffect dependency is enough.
        // But the animation takes time.

        let animationFrame;
        const loop = () => {
            updatePath();
            animationFrame = requestAnimationFrame(loop);
        };
        loop();

        return () => {
            window.removeEventListener('resize', updatePath);
            window.removeEventListener('scroll', updatePath, true);
            cancelAnimationFrame(animationFrame);
        };

    }, [hoveredNodeId, focusedNodeId, data, zoom, ancestorIds]);

    // Render as a fixed overlay on top of everything
    return (
        <svg
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 40, // Below Tooltip (100) but above cards (2/50)
            }}
        >
            <path
                d={path}
                stroke="#3b82f6"
                strokeWidth="3"
                fill="none"
                strokeLinecap="round"
                style={{
                    filter: 'drop-shadow(0 0 4px rgba(59, 130, 246, 0.5))'
                }}
            />
        </svg>
    );
};

const AggregateGroup = ({ nodes, parentName, assignedColor, parentId }) => {
    const [showAll, setShowAll] = useState(false);
    const { focusedNodeId, hoveredNodeId } = useContext(OrganogramContext);

    // Check if the group is active (contains focused or hovered node)
    const isActive = useMemo(() => {
        return nodes.some(n =>
            n.distinguishedName === focusedNodeId ||
            n.distinguishedName === hoveredNodeId
        );
    }, [nodes, focusedNodeId, hoveredNodeId]);

    // Automatically expand if the focused node is inside this group
    useEffect(() => {
        if (focusedNodeId) {
            const isFocusedInGroup = nodes.some(node => node.distinguishedName === focusedNodeId);
            if (isFocusedInGroup) {
                setShowAll(true);
            }
        }
    }, [focusedNodeId, nodes]);

    const initialLimit = 12;
    const displayNodes = showAll ? nodes : nodes.slice(0, initialLimit);
    const hasMore = nodes.length > initialLimit;

    return (
        <div
            className="aggregate-box-wrapper"
            id={`aggregate-${parentId}`}
        >
            {/* Single vertical connector from parent */}
            <div className={`connector-vertical-aggregate ${isActive ? 'active' : ''}`}></div>

            <div className={`aggregate-box ${isActive ? 'box-active' : ''}`}>
                <div className="aggregate-header">
                    <h5>Pessoas que respondem a {parentName} ({nodes.length})</h5>
                </div>
                <div className="aggregate-grid">
                    {displayNodes.map((node) => (
                        <NodeCard
                            key={node.distinguishedName}
                            node={node}
                            isGridItem={true}
                            hasChildren={false}
                            isExpanded={false}
                            toggleNode={() => {}}
                            isMatch={false}
                            parentId={null}
                            assignedColor={assignedColor}
                        />
                    ))}
                </div>
                {hasMore && (
                    <div className="aggregate-footer">
                        <button className="btn-view-more" onClick={() => setShowAll(!showAll)}>
                            {showAll ? 'Visualizar menos' : 'Visualizar mais'}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

const NodeCard = ({ node, isExpanded, toggleNode, hasChildren, isMatch, parentId, isGridItem, assignedColor }) => {
    const { hoveredNodeId, setHoveredNodeId, focusedNodeId, setFocusedNodeId, ancestorIds, setTooltipData } = useContext(OrganogramContext);

    // Use the assigned color from parent, or default to Slate-500 if root/undefined
    const nodeColor = assignedColor || '#64748b';

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

    // Tooltip timer refs
    const hoverTimer = useRef(null);

    const handleMouseEnter = (e) => {
        e.stopPropagation();
        setHoveredNodeId(nodeId);

        // Start tooltip timer
        if (hoverTimer.current) clearTimeout(hoverTimer.current);
        hoverTimer.current = setTimeout(() => {
            setTooltipData({ node, x: e.clientX, y: e.clientY });
        }, 800); // 800ms delay
    };

    const handleMouseLeave = () => {
        setHoveredNodeId(null);
        if (hoverTimer.current) clearTimeout(hoverTimer.current);
        setTooltipData(null);
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
                ${isGridItem ? 'card-grid' : ''}
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
                '--dept-color': nodeColor,
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
                        backgroundColor: isExecutive ? '#0f172a' : `${nodeColor}10`,
                        color: isExecutive ? '#fff' : nodeColor
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
                             backgroundColor: `${nodeColor}08`,
                             color: nodeColor,
                             borderColor: `${nodeColor}20`
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
    const [hoveredNodeId, setHoveredNodeId] = useState(null);
    const [focusedNodeId, setFocusedNodeId] = useState(null);
    const [ancestorIds, setAncestorIds] = useState(new Set());

    // Tooltip State
    const [tooltipData, setTooltipData] = useState(null);

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

    const handleExpandAll = () => {
        const allIds = new Set();
        const traverse = (nodes) => {
            if (!nodes) return;
            nodes.forEach(node => {
                allIds.add(node.distinguishedName);
                if (node.children) traverse(node.children);
            });
        };
        traverse(data);
        setExpandedNodes(allIds);
    };

    const handleCollapseAll = () => {
        const rootIds = new Set();
        data.forEach(node => rootIds.add(node.distinguishedName));
        setExpandedNodes(rootIds);
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
    const renderTree = (nodes, parentNode = null, parentColor = null, depth = 0) => {
        if (!nodes || !Array.isArray(nodes) || nodes.length === 0) return null;

        const GRID_THRESHOLD = 3;

        // --- Split Children Logic ---

        const branchNodes = [];
        const leafNodes = [];

        nodes.forEach(node => {
            if (node.children && node.children.length > 0) {
                branchNodes.push(node);
            } else {
                leafNodes.push(node);
            }
        });

        const totalNodes = nodes.length;
        const shouldUseAggregation = totalNodes > GRID_THRESHOLD && leafNodes.length > 0;

        let displayNodes = [];

        if (shouldUseAggregation) {
            branchNodes.sort((a, b) => a.name.localeCompare(b.name));
            displayNodes = [...branchNodes];
            if (leafNodes.length > 0) {
                displayNodes.push({
                    isAggregate: true,
                    nodes: leafNodes,
                    distinguishedName: `aggregate-${parentNode ? parentNode.distinguishedName : 'root'}`
                });
            }
        } else {
            displayNodes = nodes;
        }

        return (
            <ul
                className="org-tree"
                style={{
                    display: 'flex',
                    justifyContent: 'center',
                }}
            >
                {displayNodes.map((item, index) => {
                    if (item.isAggregate) {
                        const key = item.distinguishedName;
                        const aggColor = parentColor || getNodeColor(index + depth);

                        return (
                            <li key={key} className="org-leaf">
                                <div className="connector-vertical"></div>
                                <AggregateGroup
                                    nodes={item.nodes}
                                    parentName={parentNode ? parentNode.name : 'Unknown'}
                                    assignedColor={aggColor}
                                    parentId={parentNode ? parentNode.distinguishedName : 'root'}
                                />
                            </li>
                        );
                    }

                    const node = item;
                    const key = node.distinguishedName || index;
                    const hasChildren = node.children && node.children.length > 0;
                    const isExpanded = expandedNodes.has(key);
                    const myColor = hasChildren ? getNodeColor(index + depth) : (parentColor || getNodeColor(index + depth));

                    return (
                        <li key={key} className="org-leaf">
                            <div className="connector-vertical"></div>

                            <NodeCard
                                node={node}
                                isExpanded={isExpanded}
                                toggleNode={() => toggleNode(key)}
                                hasChildren={hasChildren}
                                isMatch={false}
                                parentId={parentNode ? parentNode.distinguishedName : null}
                                assignedColor={myColor}
                            />
                            {hasChildren && isExpanded && renderTree(node.children, node, myColor, depth + 1)}
                        </li>
                    );
                })}
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
        <OrganogramContext.Provider value={{ hoveredNodeId, setHoveredNodeId, focusedNodeId, setFocusedNodeId, ancestorIds, setTooltipData }}>
            <div className="organogram-page">
                <ActiveConnector
                    data={data}
                    hoveredNodeId={hoveredNodeId}
                    focusedNodeId={focusedNodeId}
                    ancestorIds={ancestorIds}
                    zoom={zoom}
                />
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
                            <button onClick={handleExpandAll} title="Expandir Tudo"><ChevronsDown size={16} /></button>
                            <button onClick={handleCollapseAll} title="Recolher Tudo"><ChevronsUp size={16} /></button>
                            <div className="separator"></div>
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
                        {renderTree(data, null)}
                    </div>
                </main>

                {tooltipData && (
                    <div className="node-tooltip" style={{
                        left: tooltipData.x + 20,
                        top: tooltipData.y + 20
                    }}>
                        <div className="tooltip-header">
                            Contato <ChevronRight size={14} />
                        </div>

                        {tooltipData.node.mail && (
                            <div className="tooltip-row">
                                <Mail size={16} className="icon-tooltip" />
                                <a href={`mailto:${tooltipData.node.mail}`} className="tooltip-link">
                                    {tooltipData.node.mail}
                                </a>
                            </div>
                        )}

                        {tooltipData.node.telephoneNumber && (
                            <div className="tooltip-row">
                                <Phone size={16} className="icon-tooltip" />
                                <a href={`tel:${tooltipData.node.telephoneNumber}`} className="tooltip-link">
                                    {tooltipData.node.telephoneNumber}
                                </a>
                            </div>
                        )}

                        {tooltipData.node.office && (
                            <div className="tooltip-row">
                                <MapPin size={16} className="icon-tooltip" />
                                <span className="tooltip-text">
                                    {tooltipData.node.office}
                                </span>
                            </div>
                        )}
                    </div>
                )}

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
                        padding: 60px 32px 0 32px;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                    }

                    /* --- Aggregate Box Layout --- */
                    .aggregate-box-wrapper {
                        padding-top: 60px;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        position: relative;
                        width: 100%;
                    }

                    .connector-vertical-aggregate {
                        position: absolute;
                        top: 0;
                        left: 50%;
                        width: 2px;
                        height: 60px;
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                        transition: background-color 0.2s;
                    }
                    .connector-vertical-aggregate.active {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                    }

                    .aggregate-box {
                        background: #fff;
                        border: 1px solid var(--border-color);
                        border-radius: 12px;
                        box-shadow: var(--shadow-md);
                        width: 100%;
                        max-width: 900px;
                        padding: 20px;
                        transition: border-color 0.2s, box-shadow 0.2s;
                    }
                    .aggregate-box.box-active {
                        border-color: var(--line-active);
                        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2), var(--shadow-md);
                    }

                    .aggregate-header h5 {
                        margin: 0 0 16px 0;
                        font-size: 0.95rem;
                        color: var(--text-secondary);
                        font-weight: 500;
                    }

                    .aggregate-grid {
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 16px;
                    }

                    .aggregate-footer {
                        margin-top: 16px;
                        display: flex;
                        justify-content: center;
                    }

                    .btn-view-more {
                        background: transparent;
                        border: none;
                        color: var(--line-active);
                        font-weight: 600;
                        cursor: pointer;
                        font-size: 0.9rem;
                    }
                    .btn-view-more:hover { text-decoration: underline; }

                    /* Compact User Card */
                    .compact-user-card {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        padding: 8px;
                        border-radius: 8px;
                        transition: background-color 0.2s;
                    }
                    .compact-user-card:hover {
                        background-color: #f8fafc;
                    }

                    .compact-avatar {
                        width: 36px;
                        height: 36px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: 600;
                        font-size: 0.85rem;
                        position: relative;
                        flex-shrink: 0;
                    }

                    .status-indicator {
                        position: absolute;
                        bottom: -2px;
                        right: -2px;
                        background: #fff;
                        border-radius: 50%;
                        display: flex;
                        padding: 1px;
                    }

                    .compact-info {
                        min-width: 0;
                    }

                    .compact-name {
                        font-weight: 600;
                        font-size: 0.9rem;
                        color: var(--text-primary);
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }

                    .compact-role {
                        font-size: 0.8rem;
                        color: var(--text-secondary);
                        white-space: nowrap;
                        overflow: hidden;
                        text-overflow: ellipsis;
                    }

                    /* --- Grid Layout (For large teams > 8) --- */
                    .org-grid-wrapper {
                        display: grid;
                        grid-template-columns: repeat(3, 1fr); /* 3 Columns */
                        gap: 24px;
                        padding-top: 60px; /* Space for parent connector */
                        position: relative;
                        width: 100%;
                        max-width: 1200px;
                    }

                    /* Grid Parent Connector - Vertical Stem */
                    .org-grid-wrapper::before {
                        content: '';
                        position: absolute;
                        top: 0;
                        left: 50%;
                        width: 2px;
                        height: 32px; /* Slight overlap with bus bar */
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                        transition: background-color 0.2s;
                    }

                    /* Grid Horizontal Bus Bar */
                    .org-grid-wrapper::after {
                        content: '';
                        position: absolute;
                        top: 30px; /* Starts where the stem ends */
                        left: 16.66%; /* Starts at the center of the first column (100/3/2 = 16.66) */
                        right: 16.66%; /* Ends at the center of the last column */
                        height: 2px;
                        background-color: var(--line-color);
                    }

                    .org-grid-wrapper.grid-active::before,
                    .org-grid-wrapper.grid-active::after {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                    }

                    .grid-item {
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        position: relative;
                    }

                    /* Grid Item Connections - Top Row Only */
                     .grid-item:nth-child(-n+3)::before {
                        content: '';
                        position: absolute;
                        top: -32px; /* Slight overlap with bus bar */
                        width: 2px;
                        height: 32px;
                        background-color: var(--line-color);
                        z-index: 0;
                     }

                     /* Grid Horizontal Connector (The 'Bus') */
                     /* We put a pseudo element on the grid items in the first row to connect them?
                        No, that's hard. Better to put a background line on the wrapper. */

                     .grid-item.grid-item-active::before {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                     }

                    /* Compact Card for Grid */
                    .card-grid {
                        width: 100%; /* Fill grid cell */
                        max-width: 320px;
                    }

                    /* --- Connectors --- */
                    /* Vertical line from parent (ul::before) */
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

                    /* Horizontal Arms */
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
                        border-left: none; /* REMOVED vertical line part */
                    }

                    /* New Separate Vertical Connector */
                    .connector-vertical {
                        position: absolute;
                        top: 0;
                        left: 50%;
                        width: 2px;
                        height: 60px; /* Covers the full padding-top */
                        background-color: var(--line-color);
                        transform: translateX(-50%);
                        z-index: 0;
                        transition: all 0.2s var(--ease-out);
                    }

                    /* Exceptions */
                    .tree-wrapper > .org-tree::before { display: none; }
                    .tree-wrapper > .org-tree > .org-leaf { padding-top: 0; }
                    .tree-wrapper > .org-tree > .org-leaf > .connector-vertical { display: none; } /* Root has no parent line */

                    /* Only Child: Hide horizontal arms, keep vertical */
                    .org-leaf:only-child::after { display: none; }
                    .org-leaf:only-child::before { display: none; }
                    /* Vertical connector handles the link for only-child naturally now */

                    .org-leaf:first-child::before, .org-leaf:last-child::after { border: 0 none; }

                    /* Corners */
                    .org-leaf:last-child::before {
                        border-right: 2px solid var(--line-color);
                        border-radius: 0 16px 0 0;
                    }
                    .org-leaf:first-child::after {
                        border-left: 2px solid var(--line-color); /* Add border-left back for the corner curve? No. */
                        border-radius: 16px 0 0 0;
                    }

                    .org-leaf:last-child::before { border-right: none; border-radius: 0; }
                    .org-leaf:first-child::after { border-left: none; border-radius: 0; }

                    /* Connector DOWN to children (ul::before) */
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

                    @keyframes pulse-line {
                        0% { opacity: 0.6; }
                        50% { opacity: 1; }
                        100% { opacity: 0.6; }
                    }

                    /* Left Path Highlight */
                    .org-leaf.conn-l::before {
                        border-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                        z-index: 1;
                    }

                    /* Right Path Highlight */
                    .org-leaf.conn-r::after {
                        border-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                        z-index: 1;
                    }

                    /* Vertical Stem Highlight */
                    .org-leaf.conn-v > .connector-vertical {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                        z-index: 1;
                    }

                    /* Descendant (Downward from ancestor) Highlight - LEGACY (Backup) */
                    .org-leaf.conn-descendant > ul::before {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                        z-index: 1;
                    }

                    /* Group Active Highlight (New Logic - Up to Parent) */
                    .org-tree.group-active::before {
                        background-color: var(--line-active);
                        animation: pulse-line 2s infinite ease-in-out;
                        z-index: 1;
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
                        outline: none;
                    }

                    /* Left Accent Bar */
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

                    /* Tooltip */
                    .node-tooltip {
                        position: fixed;
                        background: #fff;
                        border: 1px solid var(--border-color);
                        border-radius: 8px;
                        padding: 16px;
                        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                        z-index: 100;
                        pointer-events: auto; /* Allow clicking links */
                        width: max-content; /* Dynamic width */
                        max-width: 450px; /* Increased to accommodate long emails */
                        animation: fadeIn 0.2s ease-out;
                        color: var(--text-primary);
                    }
                    @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

                    .tooltip-header {
                        font-weight: 600;
                        font-size: 0.9rem;
                        margin-bottom: 12px;
                        display: flex;
                        align-items: center;
                        gap: 4px;
                        color: #0f172a;
                    }

                    .tooltip-row {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        margin-bottom: 8px;
                        font-size: 0.9rem;
                    }
                    .tooltip-row:last-child { margin-bottom: 0; }

                    .icon-tooltip {
                        color: #64748b;
                        flex-shrink: 0;
                    }

                    .tooltip-link {
                        color: #2563eb; /* Blue-600 */
                        text-decoration: none;
                        white-space: normal; /* Allow wrapping if needed */
                        word-break: break-word; /* Break long emails */
                    }
                    .tooltip-link:hover {
                        text-decoration: underline;
                    }

                    .tooltip-text {
                        color: #334155; /* Slate-700 */
                        white-space: normal;
                        word-break: break-word;
                    }

                `}</style>
            </div>
        </OrganogramContext.Provider>
    );
};

export default OrganogramPage;
