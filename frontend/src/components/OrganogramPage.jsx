import React, { useEffect, useState } from 'react';

const OrganogramPage = () => {
    const [data, setData] = useState([]);
    const [groupedData, setGroupedData] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [expandedDepartments, setExpandedDepartments] = useState({});
    const [useGrouping, setUseGrouping] = useState(true);

    useEffect(() => {
        fetch('/api/public/organogram_data')
            .then(res => {
                if (!res.ok) throw new Error('Falha ao carregar dados');
                return res.json();
            })
            .then(data => {
                const validData = Array.isArray(data) ? data : [];
                setData(validData);

                // Group by department
                const groups = {};
                validData.forEach(node => {
                    const dept = node.department || 'Outros / Sem Departamento';
                    if (!groups[dept]) groups[dept] = [];
                    groups[dept].push(node);
                });

                // Sort departments
                const sortedGroups = Object.keys(groups).sort().reduce((acc, key) => {
                    acc[key] = groups[key];
                    return acc;
                }, {});

                setGroupedData(sortedGroups);
                setLoading(false);
            })
            .catch(err => {
                setError(err.message);
                setLoading(false);
            });
    }, []);

    const toggleDepartment = (dept) => {
        setExpandedDepartments(prev => ({
            ...prev,
            [dept]: !prev[dept]
        }));
    };

    const getInitials = (name) => {
        if (!name) return '';
        const names = name.split(' ');
        if (names.length >= 2) return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase();
        return name[0].toUpperCase();
    };

    // Função recursiva para renderizar a árvore
    const renderTree = (nodes) => {
        if (!nodes || !Array.isArray(nodes) || nodes.length === 0) return null;

        return (
            <ul className="org-tree-ul">
                {nodes.map((node, index) => {
                    const isMatch = searchTerm && node.name && node.name.toLowerCase().includes(searchTerm.toLowerCase());
                    const nodeClass = `org-node ${isMatch ? 'highlight-node' : ''}`;

                    return (
                        <li key={node.distinguishedName || index} className="org-tree-li">
                            <div className={nodeClass} id={`node-${index}`}>
                                <div className="avatar">
                                    {getInitials(node.name)}
                                </div>
                                <div className="node-content">
                                    <h6>{node.name}</h6>
                                    <p className="title">{node.title}</p>
                                    <p className="department">{node.department}</p>
                                </div>
                            </div>
                            {node.children && node.children.length > 0 && renderTree(node.children)}
                        </li>
                    );
                })}
            </ul>
        );
    };

    const renderGroupedView = () => {
        const departments = Object.keys(groupedData);
        if (departments.length === 0) return <div className="no-data">Nenhum dado encontrado para o organograma.</div>;

        return (
            <div className="departments-grid">
                {departments.map(dept => (
                    <div key={dept} className="department-section">
                        <div
                            className="department-header"
                            onClick={() => toggleDepartment(dept)}
                        >
                            <h3><i className="fas fa-building me-2"></i> {dept}</h3>
                            <div className="badge-count">{groupedData[dept].length} {groupedData[dept].length === 1 ? 'Líder' : 'Líderes'}</div>
                            <i className={`fas fa-chevron-${expandedDepartments[dept] ? 'up' : 'down'} toggle-icon`}></i>
                        </div>

                        {expandedDepartments[dept] && (
                            <div className="department-tree-container">
                                <div className="org-tree-wrapper">
                                    {renderTree(groupedData[dept])}
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        );
    };

    if (loading) return <div className="loading-container"><div className="spinner"></div> Carregando organograma...</div>;
    if (error) return <div className="error-container">Erro: {error}</div>;

    return (
        <div className="organogram-page">
            <div className="header-container">
                <h2><i className="fas fa-sitemap"></i> Organograma</h2>
                <div className="controls">
                    <div className="view-toggle">
                        <button
                            className={`btn-toggle ${useGrouping ? 'active' : ''}`}
                            onClick={() => setUseGrouping(true)}
                            title="Agrupar por Departamento"
                        >
                            <i className="fas fa-layer-group"></i> Departamentos
                        </button>
                        <button
                            className={`btn-toggle ${!useGrouping ? 'active' : ''}`}
                            onClick={() => setUseGrouping(false)}
                            title="Visualização Completa"
                        >
                            <i className="fas fa-stream"></i> Completo
                        </button>
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
                {useGrouping ? (
                    renderGroupedView()
                ) : (
                    <div className="org-tree-wrapper">
                        {renderTree(data)}
                    </div>
                )}
            </div>

            <style>{`
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
                    margin-bottom: 20px;
                    background: white;
                    padding: 15px 30px;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    flex-wrap: wrap;
                    gap: 15px;
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

                .view-toggle {
                    display: flex;
                    background: #f8f9fa;
                    border-radius: 20px;
                    padding: 3px;
                    border: 1px solid #dee2e6;
                }
                .btn-toggle {
                    border: none;
                    background: transparent;
                    padding: 6px 15px;
                    border-radius: 15px;
                    cursor: pointer;
                    font-size: 0.85rem;
                    color: #6c757d;
                    transition: all 0.2s;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                .btn-toggle.active {
                    background: white;
                    color: #007bff;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    font-weight: 600;
                }

                .loading-container, .error-container {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    font-size: 1.2rem;
                    color: #6c757d;
                }

                .organogram-scroll-container {
                    overflow: auto;
                    background: white;
                    border-radius: 12px;
                    padding: 30px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                    min-height: 80vh;
                }

                /* Department Grouping */
                .departments-grid {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                }
                .department-section {
                    background: #fff;
                    border: 1px solid #eee;
                    border-radius: 10px;
                    overflow: hidden;
                }
                .department-header {
                    padding: 15px 20px;
                    background: #f8f9fa;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    transition: background 0.2s;
                }
                .department-header:hover {
                    background: #e9ecef;
                }
                .department-header h3 {
                    margin: 0;
                    font-size: 1.1rem;
                    color: #495057;
                    flex: 1;
                }
                .badge-count {
                    background: #007bff;
                    color: white;
                    padding: 2px 10px;
                    border-radius: 10px;
                    font-size: 0.8rem;
                    margin-right: 15px;
                }
                .toggle-icon {
                    color: #adb5bd;
                }
                .department-tree-container {
                    padding: 20px;
                    overflow-x: auto;
                    background: #fff;
                    border-top: 1px solid #eee;
                }

                /* Tree CSS */
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
