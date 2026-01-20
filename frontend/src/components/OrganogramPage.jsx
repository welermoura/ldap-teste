import React, { useEffect, useState, useMemo } from 'react';

// --- Utility Functions ---

// Generate a deterministic color based on a string (Department)
const stringToColor = (str) => {
    if (!str) return '#cbd5e1'; // Slate-300 for no department
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    // Pastel/Corporate Palette restricted generation
    const hue = Math.abs(hash % 360);
    return `hsl(${hue}, 65%, 45%)`; // Controlled saturation/lightness for professional look
};

const getInitials = (name) => {
    if (!name) return '';
    const names = name.split(' ');
    if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
    return name[0].toUpperCase();
};

// --- Components ---

const NodeCard = ({ node, isExpanded, toggleNode, hasChildren, isMatch }) => {
    const deptColor = useMemo(() => stringToColor(node.department), [node.department]);

    // Check for "Presidente" or "CEO" to style differently
    const isExecutive = node.title && (
        node.title.toLowerCase().includes('presidente') ||
        node.title.toLowerCase().includes('ceo') ||
        node.title.toLowerCase().includes('diretor')
    );

    return (
        <div
            className={`org-card ${isMatch ? 'highlight' : ''} ${isExecutive ? 'executive' : ''}`}
            onClick={() => hasChildren && toggleNode()}
            style={{ borderLeftColor: deptColor }}
        >
            <div className="card-header">
                <div className="avatar" style={{ backgroundColor: isExecutive ? '#1e293b' : '#f1f5f9', color: isExecutive ? '#fff' : '#475569' }}>
                    {getInitials(node.name)}
                </div>
                <div className="info">
                    <h6 className="name">{node.name}</h6>
                    <p className="role">{node.title || 'Cargo não definido'}</p>
                </div>
            </div>

            {node.department && (
                <div className="card-footer">
                    <span className="dept-badge" style={{ backgroundColor: `${deptColor}20`, color: deptColor }}>
                        {node.department}
                    </span>
                </div>
            )}

            {hasChildren && (
                <div className="toggle-btn">
                    <i className={`fas fa-chevron-${isExpanded ? 'up' : 'down'}`}></i>
                </div>
            )}
        </div>
    );
};

const OrganogramPage = () => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [zoom, setZoom] = useState(1);
    const [expandedNodes, setExpandedNodes] = useState(new Set());

    useEffect(() => {
        fetch('/api/public/organogram_data')
            .then(res => {
                if (!res.ok) throw new Error('Falha ao carregar dados');
                return res.json();
            })
            .then(data => {
                const validData = Array.isArray(data) ? data : [];
                setData(validData);

                // Initially expand roots
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

    const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.1, 2));
    const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.1, 0.3));
    const handleResetZoom = () => setZoom(1);

    const renderTree = (nodes) => {
        if (!nodes || !Array.isArray(nodes) || nodes.length === 0) return null;

        return (
            <ul className="org-tree">
                {nodes.map((node, index) => {
                    const isMatch = searchTerm && node.name && node.name.toLowerCase().includes(searchTerm.toLowerCase());
                    const key = node.distinguishedName || index;
                    const hasChildren = node.children && node.children.length > 0;
                    const isExpanded = expandedNodes.has(key);

                    return (
                        <li key={key} className="org-leaf">
                            <NodeCard
                                node={node}
                                isExpanded={isExpanded}
                                toggleNode={() => toggleNode(key)}
                                hasChildren={hasChildren}
                                isMatch={isMatch}
                            />
                            {hasChildren && isExpanded && renderTree(node.children)}
                        </li>
                    );
                })}
            </ul>
        );
    };

    if (loading) return <div className="loading-container"><div className="spinner"></div> Carregando organograma...</div>;
    if (error) return <div className="error-container">Erro: {error}</div>;

    return (
        <div className="organogram-page">
            <header className="page-header">
                <div className="brand">
                    <i className="fas fa-network-wired"></i>
                    <h2>Estrutura Organizacional</h2>
                </div>

                <div className="actions">
                    <div className="search-wrapper">
                        <i className="fas fa-search"></i>
                        <input
                            type="text"
                            placeholder="Buscar colaborador..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>

                    <div className="zoom-wrapper">
                        <button onClick={handleZoomOut} aria-label="Zoom Out"><i className="fas fa-minus"></i></button>
                        <span>{Math.round(zoom * 100)}%</span>
                        <button onClick={handleZoomIn} aria-label="Zoom In"><i className="fas fa-plus"></i></button>
                        <button onClick={handleResetZoom} aria-label="Reset Zoom"><i className="fas fa-redo"></i></button>
                    </div>

                    <a href="/login" className="btn-login">Login</a>
                </div>
            </header>

            <main className="canvas">
                <div
                    className="tree-container"
                    style={{
                        transform: `scale(${zoom})`,
                        transformOrigin: 'top center'
                    }}
                >
                    {renderTree(data)}
                </div>
            </main>

            <style>{`
                /* --- Variables --- */
                :root {
                    --bg-page: #f8fafc;
                    --bg-card: #ffffff;
                    --text-primary: #1e293b;
                    --text-secondary: #64748b;
                    --border-color: #e2e8f0;
                    --primary-color: #0f172a;
                    --accent-color: #3b82f6;
                    --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
                    --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -1px rgb(0 0 0 / 0.06);
                    --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
                }

                /* --- Layout --- */
                .organogram-page {
                    font-family: 'Inter', 'Segoe UI', sans-serif;
                    background-color: var(--bg-page);
                    min-height: 100vh;
                    display: flex;
                    flex-direction: column;
                    color: var(--text-primary);
                }

                /* --- Header --- */
                .page-header {
                    background: rgba(255, 255, 255, 0.9);
                    backdrop-filter: blur(8px);
                    border-bottom: 1px solid var(--border-color);
                    padding: 16px 32px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    position: sticky;
                    top: 0;
                    z-index: 50;
                    box-shadow: var(--shadow-sm);
                }

                .brand {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    color: var(--primary-color);
                }
                .brand i { font-size: 1.25rem; }
                .brand h2 { margin: 0; font-size: 1.25rem; font-weight: 600; letter-spacing: -0.025em; }

                .actions {
                    display: flex;
                    align-items: center;
                    gap: 20px;
                }

                /* Search */
                .search-wrapper {
                    position: relative;
                }
                .search-wrapper i {
                    position: absolute;
                    left: 12px;
                    top: 50%;
                    transform: translateY(-50%);
                    color: var(--text-secondary);
                    font-size: 0.875rem;
                }
                .search-wrapper input {
                    padding: 8px 12px 8px 36px;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    font-size: 0.875rem;
                    width: 240px;
                    transition: all 0.2s;
                    background: var(--bg-page);
                }
                .search-wrapper input:focus {
                    outline: none;
                    border-color: var(--accent-color);
                    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
                    background: #fff;
                }

                /* Zoom */
                .zoom-wrapper {
                    display: flex;
                    align-items: center;
                    background: #fff;
                    border: 1px solid var(--border-color);
                    border-radius: 8px;
                    padding: 4px;
                }
                .zoom-wrapper button {
                    background: transparent;
                    border: none;
                    width: 28px;
                    height: 28px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    color: var(--text-secondary);
                    border-radius: 4px;
                    transition: all 0.2s;
                }
                .zoom-wrapper button:hover {
                    background: var(--bg-page);
                    color: var(--primary-color);
                }
                .zoom-wrapper span {
                    font-size: 0.75rem;
                    font-weight: 600;
                    width: 40px;
                    text-align: center;
                    color: var(--text-primary);
                }

                .btn-login {
                    background: var(--primary-color);
                    color: #fff;
                    text-decoration: none;
                    padding: 8px 16px;
                    border-radius: 8px;
                    font-size: 0.875rem;
                    font-weight: 500;
                    transition: opacity 0.2s;
                }
                .btn-login:hover { opacity: 0.9; }

                /* --- Canvas --- */
                .canvas {
                    flex: 1;
                    overflow: auto;
                    padding: 60px;
                    cursor: grab;
                }
                .canvas:active { cursor: grabbing; }

                /* --- Tree Layout --- */
                .tree-container {
                    display: flex;
                    justify-content: center;
                    width: max-content;
                    min-width: 100%;
                    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                }

                .org-tree {
                    display: flex;
                    justify-content: center;
                    padding: 0;
                    margin: 0;
                    list-style: none;
                    position: relative;
                }

                .org-leaf {
                    position: relative;
                    padding: 40px 16px 0 16px; /* Spacing between levels */
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }

                /* --- Connectors (Lines) --- */
                /* Vertical line from parent bottom */
                .org-tree::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 50%;
                    transform: translateX(-50%);
                    width: 1px;
                    height: 20px; /* Connects to parent */
                    background-color: #cbd5e1;
                }

                /* Exception: Root node needs no top connector */
                .tree-container > .org-tree::before { display: none; }
                .tree-container > .org-tree > .org-leaf { padding-top: 0; }

                /* Horizontal line above children */
                .org-leaf::before, .org-leaf::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    right: 50%;
                    border-top: 1px solid #cbd5e1;
                    width: 50%;
                    height: 20px;
                }
                .org-leaf::after {
                    right: auto;
                    left: 50%;
                    border-left: 1px solid #cbd5e1;
                }

                /* Remove connectors for single/first/last children */
                .org-leaf:only-child::after, .org-leaf:only-child::before { display: none; }
                .org-leaf:only-child { padding-top: 0; }
                .org-leaf:first-child::before, .org-leaf:last-child::after { border: 0 none; }

                /* Curved corners */
                .org-leaf:last-child::before {
                    border-right: 1px solid #cbd5e1;
                    border-radius: 0 12px 0 0;
                }
                .org-leaf:first-child::after {
                    border-radius: 12px 0 0 0;
                }

                /* Vertical line from card down to children */
                .org-leaf > ul::before {
                    content: '';
                    position: absolute;
                    top: -20px; /* Move up to connect to card */
                    left: 50%;
                    width: 1px;
                    height: 20px;
                    background-color: #cbd5e1;
                    transform: translateX(-50%);
                }

                /* --- Card Design --- */
                .org-card {
                    background: var(--bg-card);
                    border: 1px solid var(--border-color);
                    border-left: 4px solid var(--text-secondary); /* Default accent */
                    border-radius: 12px;
                    padding: 16px;
                    width: 260px;
                    position: relative;
                    box-shadow: var(--shadow-sm);
                    transition: all 0.3s ease;
                    z-index: 10;
                    cursor: pointer;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                .org-card:hover {
                    transform: translateY(-4px);
                    box-shadow: var(--shadow-lg);
                    border-color: #cbd5e1;
                }

                .org-card.highlight {
                    border-color: #fbbf24;
                    background-color: #fffbeb;
                }

                .org-card.executive {
                    border-left-width: 6px;
                }

                .card-header {
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                }

                .avatar {
                    width: 48px;
                    height: 48px;
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: 700;
                    font-size: 1.125rem;
                    flex-shrink: 0;
                }

                .info {
                    flex: 1;
                    min-width: 0; /* Text truncation fix */
                }

                .name {
                    margin: 0;
                    font-size: 0.95rem;
                    font-weight: 600;
                    color: var(--text-primary);
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    line-height: 1.4;
                }

                .role {
                    margin: 2px 0 0 0;
                    font-size: 0.8rem;
                    color: var(--text-secondary);
                    line-height: 1.3;
                    display: -webkit-box;
                    -webkit-line-clamp: 2;
                    -webkit-box-orient: vertical;
                    overflow: hidden;
                }

                .card-footer {
                    border-top: 1px solid var(--bg-page);
                    padding-top: 10px;
                    display: flex;
                }

                .dept-badge {
                    font-size: 0.7rem;
                    font-weight: 600;
                    padding: 4px 8px;
                    border-radius: 6px;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }

                /* Toggle Button */
                .toggle-btn {
                    position: absolute;
                    bottom: -12px;
                    left: 50%;
                    transform: translateX(-50%);
                    width: 24px;
                    height: 24px;
                    background: #fff;
                    border: 1px solid var(--border-color);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 0.75rem;
                    color: var(--text-secondary);
                    box-shadow: var(--shadow-sm);
                    transition: all 0.2s;
                }
                .org-card:hover .toggle-btn {
                    border-color: var(--accent-color);
                    color: var(--accent-color);
                }

                /* Loading/Error */
                .loading-container, .error-container {
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background: var(--bg-page);
                    color: var(--text-secondary);
                }
                .spinner {
                    border: 3px solid #e2e8f0;
                    border-top: 3px solid var(--accent-color);
                    border-radius: 50%;
                    width: 32px;
                    height: 32px;
                    animation: spin 1s linear infinite;
                    margin-bottom: 16px;
                }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            `}</style>
        </div>
    );
};

export default OrganogramPage;
