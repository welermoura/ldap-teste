import React, { useEffect, useState } from 'react';

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

                // Inicialmente expande apenas os nós raiz
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

    const getInitials = (name) => {
        if (!name) return '';
        const names = name.split(' ');
        if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
        return name[0].toUpperCase();
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

    const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.1, 2));
    const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.1, 0.3));
    const handleResetZoom = () => setZoom(1);

    // Função recursiva para renderizar a árvore
    const renderTree = (nodes) => {
        if (!nodes || !Array.isArray(nodes) || nodes.length === 0) return null;

        return (
            <ul className="org-tree-ul">
                {nodes.map((node, index) => {
                    const isMatch = searchTerm && node.name && node.name.toLowerCase().includes(searchTerm.toLowerCase());
                    const nodeClass = `org-node ${isMatch ? 'highlight-node' : ''}`;
                    const key = node.distinguishedName || index;
                    const hasChildren = node.children && node.children.length > 0;
                    const isExpanded = expandedNodes.has(key);

                    // Auto-expand if search matches this node or a child (simplified: just this node for now)
                    if (isMatch && !isExpanded && hasChildren) {
                        // This side-effect in render is not ideal, but for search highlighting it's often acceptable or handled via useEffect
                    }

                    return (
                        <li key={key} className="org-tree-li">
                            <div className={nodeClass} id={`node-${index}`}>
                                <div className="avatar">
                                    {getInitials(node.name)}
                                </div>
                                <div className="node-content">
                                    <h6>{node.name}</h6>
                                    <p className="title">{node.title}</p>
                                    <p className="department">{node.department}</p>
                                </div>
                                {hasChildren && (
                                    <button
                                        className="btn-expand"
                                        onClick={(e) => {
                                            e.stopPropagation(); // Prevent card click if we add one later
                                            toggleNode(key);
                                        }}
                                        title={isExpanded ? "Recolher" : "Expandir"}
                                    >
                                        <i className={`fas fa-chevron-${isExpanded ? 'up' : 'down'}`}></i>
                                    </button>
                                )}
                            </div>
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
            <div className="header-container">
                <h2><i className="fas fa-sitemap"></i> Organograma</h2>
                <div className="controls">
                    <div className="zoom-controls">
                        <button onClick={handleZoomOut} title="Diminuir Zoom"><i className="fas fa-minus"></i></button>
                        <span className="zoom-level">{Math.round(zoom * 100)}%</span>
                        <button onClick={handleZoomIn} title="Aumentar Zoom"><i className="fas fa-plus"></i></button>
                        <button onClick={handleResetZoom} title="Resetar Zoom"><i className="fas fa-redo"></i></button>
                    </div>
                    <div className="search-box">
                        <input
                            type="text"
                            placeholder="Buscar colaborador..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            className="form-control glass-input"
                        />
                    </div>
                    <a href="/login" className="btn-login">Login</a>
                </div>
            </div>

            <div className="organogram-scroll-container">
                <div
                    className="org-tree-wrapper"
                    style={{
                        transform: `scale(${zoom})`,
                        transformOrigin: 'top center'
                    }}
                >
                    {renderTree(data)}
                </div>
            </div>

            <style>{`
                .organogram-page {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #f0f2f5 0%, #e1e5ea 100%);
                    min-height: 100vh;
                    color: #333;
                    padding: 20px;
                    overflow: hidden; /* Prevent body scroll if zoom goes huge */
                    display: flex;
                    flex-direction: column;
                }
                .header-container {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    background: white;
                    padding: 15px 30px;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    flex-wrap: wrap;
                    gap: 15px;
                    z-index: 10;
                    position: relative;
                }
                .header-container h2 {
                    margin: 0;
                    font-size: 1.5rem;
                    color: #2c3e50;
                }
                .controls {
                    display: flex;
                    align-items: center;
                    gap: 15px;
                    flex-wrap: wrap;
                }

                .zoom-controls {
                    display: flex;
                    align-items: center;
                    background: #f8f9fa;
                    border-radius: 20px;
                    padding: 3px;
                    border: 1px solid #dee2e6;
                }
                .zoom-controls button {
                    border: 1px solid #dee2e6; /* Added border for visibility */
                    background: white; /* Changed background for visibility */
                    width: 30px;
                    height: 30px;
                    border-radius: 50%;
                    cursor: pointer;
                    color: #495057; /* Darker color for visibility */
                    transition: all 0.2s;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 2px;
                }
                .zoom-controls button:hover {
                    background: #007bff;
                    color: white;
                    border-color: #007bff;
                }
                .zoom-level {
                    font-size: 0.85rem;
                    color: #495057;
                    min-width: 45px;
                    text-align: center;
                    font-weight: 600;
                }

                .search-box input {
                    background: #f8f9fa;
                    border: 1px solid #dee2e6;
                    color: #495057;
                    padding: 8px 20px;
                    border-radius: 20px;
                    outline: none;
                    width: 250px;
                    transition: border-color 0.3s;
                }
                .search-box input:focus {
                    border-color: #007bff;
                }
                .btn-login {
                    color: #007bff;
                    text-decoration: none;
                    border: 1px solid #007bff;
                    padding: 6px 20px;
                    border-radius: 20px;
                    transition: all 0.3s;
                    font-weight: 600;
                    font-size: 0.9rem;
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

                /* Tree CSS - Flexbox approach */
                .organogram-scroll-container {
                    overflow: auto;
                    background: white;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    flex: 1; /* Take remaining height */
                    position: relative;
                }

                .org-tree-wrapper {
                    display: flex;
                    justify-content: center;
                    width: fit-content;
                    min-width: 100%;
                    transition: transform 0.3s ease; /* Smooth zoom */
                }

                .org-tree-ul {
                    padding-top: 20px;
                    position: relative;
                    display: flex;
                    justify-content: center;
                    margin: 0;
                    padding-left: 0;
                }

                .org-tree-li {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    position: relative;
                    padding: 20px 10px 0 10px;
                    box-sizing: border-box;
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
                    transform: translateX(-50%);
                }

                /* HIDE connectors for the very top level roots */
                .org-tree-wrapper > .org-tree-ul > .org-tree-li::before,
                .org-tree-wrapper > .org-tree-ul > .org-tree-li::after {
                    display: none;
                }
                .org-tree-wrapper > .org-tree-ul > .org-tree-li {
                    padding-top: 0;
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
                    margin-bottom: 0;
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

                /* Expand Button - Minimalist arrow only */
                .btn-expand {
                    border: none;
                    background: transparent;
                    color: #6c757d;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 14px; /* Larger icon */
                    cursor: pointer;
                    margin-top: 5px;
                    transition: all 0.2s;
                    width: 100%; /* Full width click area */
                    height: 20px;
                }
                .btn-expand:hover {
                    color: #007bff;
                    background: #f8f9fa; /* Subtle background on hover */
                    border-radius: 4px;
                }

                /* Hover effects on lines */
                .org-node:hover+ul li::after,
                .org-node:hover+ul li::before,
                .org-node:hover+ul::before,
                .org-node:hover+ul ul::before{
                    border-color: #007bff;
                }
            `}</style>
        </div>
    );
};

export default OrganogramPage;
