import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Search, X, User } from 'lucide-react';

const OrganogramSearch = ({ data, onSelect }) => {
    const [query, setQuery] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const wrapperRef = useRef(null);

    // Indexar dados (flatten tree)
    const searchIndex = useMemo(() => {
        const index = [];
        const traverse = (nodes) => {
            if (!nodes) return;
            nodes.forEach(node => {
                index.push({
                    name: node.name,
                    title: node.title,
                    department: node.department,
                    id: node.distinguishedName,
                    distinguishedName: node.distinguishedName
                });
                if (node.children) traverse(node.children);
            });
        };
        traverse(data);
        return index;
    }, [data]);

    // Filtrar resultados
    const results = useMemo(() => {
        if (!query || query.length < 2) return [];
        const lowerQuery = query.toLowerCase();
        return searchIndex
            .filter(item => item.name && item.name.toLowerCase().includes(lowerQuery))
            .slice(0, 8);
    }, [query, searchIndex]);

    // Fechar ao clicar fora
    useEffect(() => {
        const handleClickOutside = (event) => {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleSelect = (item) => {
        setQuery(item.name);
        setIsOpen(false);
        onSelect(item.id);
    };

    const handleClear = () => {
        setQuery('');
        setIsOpen(false);
    };

    return (
        <div className="search-component" ref={wrapperRef}>
            <div className={`search-input-wrapper ${isOpen ? 'active' : ''}`}>
                <Search size={16} className="search-icon" />
                <input
                    type="text"
                    placeholder="Buscar colaborador..."
                    value={query}
                    onChange={(e) => {
                        setQuery(e.target.value);
                        setIsOpen(true);
                    }}
                    onFocus={() => setIsOpen(true)}
                />
                {query && (
                    <button className="clear-btn" onClick={handleClear}>
                        <X size={14} />
                    </button>
                )}
            </div>

            {isOpen && results.length > 0 && (
                <div className="search-dropdown">
                    {results.map((result) => (
                        <div
                            key={result.id}
                            className="search-item"
                            onClick={() => handleSelect(result)}
                        >
                            <div className="item-avatar">
                                <User size={16} />
                            </div>
                            <div className="item-info">
                                <span className="item-name">{result.name}</span>
                                <span className="item-meta">
                                    {result.title} • {result.department}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {isOpen && query.length >= 2 && results.length === 0 && (
                <div className="search-dropdown empty">
                    <span>Nenhum resultado encontrado</span>
                </div>
            )}

            <style>{`
                .search-component {
                    position: relative;
                    width: 300px;
                }
                .search-input-wrapper {
                    display: flex;
                    align-items: center;
                    background: #fff;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    padding: 8px 12px;
                    transition: all 0.2s;
                    position: relative;
                }
                .search-input-wrapper:focus-within {
                    border-color: #3b82f6;
                    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
                }
                .search-icon {
                    color: #94a3b8;
                    margin-right: 8px;
                }
                .search-input-wrapper input {
                    border: none;
                    outline: none;
                    width: 100%;
                    font-size: 0.9rem;
                    color: #0f172a;
                }
                .clear-btn {
                    background: none;
                    border: none;
                    color: #94a3b8;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    padding: 4px;
                }
                .clear-btn:hover { color: #64748b; }

                .search-dropdown {
                    position: absolute;
                    top: 100%;
                    left: 0;
                    right: 0;
                    margin-top: 8px;
                    background: #fff;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
                    max-height: 300px;
                    overflow-y: auto;
                    z-index: 100;
                    padding: 4px;
                }
                .search-item {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    padding: 8px 12px;
                    border-radius: 6px;
                    cursor: pointer;
                    transition: background 0.15s;
                }
                .search-item:hover {
                    background: #f1f5f9;
                }
                .item-avatar {
                    width: 32px;
                    height: 32px;
                    background: #e2e8f0;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: #64748b;
                }
                .item-info {
                    display: flex;
                    flex-direction: column;
                    overflow: hidden;
                }
                .item-name {
                    font-weight: 500;
                    font-size: 0.9rem;
                    color: #0f172a;
                }
                .item-meta {
                    font-size: 0.75rem;
                    color: #64748b;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                .search-dropdown.empty {
                    padding: 16px;
                    text-align: center;
                    color: #94a3b8;
                    font-size: 0.9rem;
                }
            `}</style>
        </div>
    );
};

export default OrganogramSearch;
