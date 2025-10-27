import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import axios from 'axios';
import { DndProvider, useDrag } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { ItemTypes } from './dndTypes';
import EditUserModal from './EditUserModal';
import DisableTempModal from './DisableTempModal';
import ScheduleAbsenceModal from './ScheduleAbsenceModal';
import MoveModal from './MoveModal';
import NotificationModal from './NotificationModal';
import TreeNode from './TreeNode';
import './ADTree.css';

const DraggableItem = ({ member, getIcon, onContextMenu }) => {
    const [{ isDragging }, drag] = useDrag(() => ({
        type: ItemTypes.AD_OBJECT,
        item: { dn: member.dn, name: member.name, type: member.type },
        collect: (monitor) => ({
            isDragging: !!monitor.isDragging(),
        }),
        canDrag: member.status !== 'Excluído',
    }));

    return (
        <li
            ref={member.status !== 'Excluído' ? drag : null}
            className="member-item"
            style={{
                opacity: isDragging ? 0.5 : 1,
                cursor: member.status === 'Excluído' ? 'default' : 'move'
            }}
            onContextMenu={(e) => onContextMenu(e, member)}
        >
            {getIcon(member.type, member.status === 'Excluído')}
            <div className="member-info">
                <span className="member-name">{member.name}</span>
                {member.ou_path && <span className="member-ou-path">{member.ou_path}</span>}
            </div>
        </li>
    );
};

const ContextMenu = ({ x, y, show, onClose, targetNode, permissions, onEdit, onToggleStatus, onResetPassword, onDelete, onDisableTemp, onScheduleAbsence, onMove, onRestore }) => {
    if (!show || !targetNode) return null;

    const style = { top: y, left: x };
    const isUser = targetNode.type === 'user';
    const isComputer = targetNode.type === 'computer';
    const isDeleted = targetNode.status === 'Excluído';

    const renderMenuItem = (key, icon, text, action, condition) => {
        if (!condition) return null;
        return <li key={key} onClick={() => { action(targetNode); onClose(); }}><i className={`fas ${icon} me-2`}></i>{text}</li>;
    };

    if (isDeleted) {
        return createPortal(
            <div className="context-menu" style={style} onMouseLeave={onClose}>
                <ul>
                    {renderMenuItem('restore', 'fa-undo', 'Restaurar', onRestore, true)}
                </ul>
            </div>,
            document.body
        );
    }

    const userActions = [
        renderMenuItem('move', 'fa-arrows-alt', 'Mover', onMove, permissions.can_move_user),
        renderMenuItem('edit', 'fa-user-edit', 'Editar', onEdit, permissions.can_edit),
        renderMenuItem('toggle', 'fa-ban', 'Ativar/Desativar Conta', onToggleStatus, permissions.can_disable),
        renderMenuItem('reset_password', 'fa-key', 'Resetar Senha', onResetPassword, permissions.can_reset_password),
        renderMenuItem('disable_temp', 'fa-user-clock', 'Desativar por X dias', onDisableTemp, permissions.can_disable),
        renderMenuItem('schedule_absence', 'fa-calendar-alt', 'Agendar Ausência', onScheduleAbsence, permissions.can_disable),
    ];

    const computerActions = [
        renderMenuItem('move_computer', 'fa-arrows-alt', 'Mover', onMove, permissions.can_move_user),
        renderMenuItem('delete_computer', 'fa-trash-alt', 'Excluir', onDelete, permissions.can_delete_user),
    ];

    const visibleUserActions = userActions.filter(Boolean);

    return createPortal(
        <div className="context-menu" style={style} onMouseLeave={onClose}>
            <ul>
                {isUser && visibleUserActions}
                {isComputer && computerActions}
                {isUser && permissions.can_delete_user && visibleUserActions.length > 0 && <li className="separator"></li>}
                {isUser && renderMenuItem('delete_user', 'fa-trash-alt', 'Excluir', onDelete, permissions.can_delete_user)}
            </ul>
        </div>,
        document.body
    );
};

const ContentPanel = ({ selectedNode, members, getIcon, onOuDoubleClick, isSearchMode, onContextMenu }) => {
    const hasMembers = members && members.length > 0;
    const isRecycleBin = selectedNode && selectedNode.dn === 'recycle_bin';

    if (isSearchMode && !hasMembers) {
        return (
            <div className="content-panel">
                <h4 className="content-header">Resultados da Busca</h4>
                <div className="content-placeholder">Nenhum usuário ou computador encontrado.</div>
            </div>
        );
    }

    // Tabela para a lixeira
    if (isRecycleBin) {
        return (
            <div className="content-panel">
                <h4 className="content-header"><i className="fas fa-recycle me-2"></i>Lixeira</h4>
                {hasMembers ? (
                    <table className="table table-hover table-sm">
                        <thead>
                            <tr>
                                <th>Nome</th>
                                <th>Cargo</th>
                                <th>OU Original</th>
                                <th>Data da Exclusão</th>
                            </tr>
                        </thead>
                        <tbody>
                            {members.map(member => (
                                <tr key={member.dn} onContextMenu={(e) => onContextMenu(e, member)}>
                                    <td>{getIcon(member.type, true)} {member.name}</td>
                                    <td>{member.title}</td>
                                    <td>{member.originalOU}</td>
                                    <td>{member.deletedDate}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="content-placeholder">A lixeira está vazia.</div>
                )}
            </div>
        );
    }

    if (!isSearchMode && selectedNode && !hasMembers) {
        return (
            <div className="content-panel">
                <h4 className="content-header">Conteúdo de: {selectedNode.text || selectedNode.name}</h4>
                <div className="content-placeholder">Esta Unidade Organizacional está vazia.</div>
            </div>
        );
    }

    if (!isSearchMode && !selectedNode) {
        return (
            <div className="content-panel">
                <div className="content-placeholder">Selecione uma Unidade Organizacional na árvore para ver seu conteúdo.</div>
            </div>
        );
    }

    const headerText = isSearchMode ? "Resultados da Busca" : `Conteúdo de: ${selectedNode.text || selectedNode.name}`;

    return (
        <div className="content-panel">
            <h4 className="content-header">{headerText}</h4>
            <ul className="member-list">
                {members.map(member => {
                    if (isSearchMode && (member.type === 'user' || member.type === 'computer')) {
                        return <DraggableItem key={member.dn} member={member} getIcon={getIcon} onContextMenu={onContextMenu} />;
                    }
                    if (!isSearchMode && (member.type === 'user' || member.type === 'group' || member.type === 'computer')) {
                        return <DraggableItem key={member.dn} member={member} getIcon={getIcon} onContextMenu={onContextMenu} />;
                    } else if (!isSearchMode && member.type === 'ou') {
                        return (
                            <li key={member.dn} className="member-item non-draggable" onDoubleClick={() => onOuDoubleClick(member)} style={{ cursor: 'pointer' }} onContextMenu={(e) => onContextMenu(e, member)}>
                                {getIcon(member.type)}
                                <span className="member-name">{member.name}</span>
                            </li>
                        );
                    } else {
                        return (
                            <li key={member.dn} className="member-item non-draggable">
                                {getIcon(member.type)}
                                <span className="member-name">{member.name}</span>
                            </li>
                        );
                    }
                })}
            </ul>
        </div>
    );
};


const ConfirmationModal = ({ isOpen, onClose, onConfirm, title, children }) => {
    if (!isOpen) return null;

    return (
        <div className="modal-backdrop">
            <div className="modal-content">
                <div className="modal-header">
                    <h5 className="modal-title">{title}</h5>
                    <button type="button" className="btn-close" onClick={onClose}></button>
                </div>
                <div className="modal-body">{children}</div>
                <div className="modal-footer">
                    <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
                    <button type="button" className="btn btn-primary" onClick={onConfirm}>Confirmar</button>
                </div>
            </div>
        </div>
    );
};

const ADExplorerPage = () => {
    const [treeData, setTreeData] = useState([]);
    const [selectedNode, setSelectedNode] = useState(null);
    const [members, setMembers] = useState([]);
    const [isMoveModalOpen, setIsMoveModalOpen] = useState(false);
    const [moveDetails, setMoveDetails] = useState(null);
    const [confirmationAction, setConfirmationAction] = useState({ isOpen: false });
    const [searchQuery, setSearchQuery] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [isSearchLoading, setIsSearchLoading] = useState(false);
    const [searchPerformed, setSearchPerformed] = useState(false);
    const [contextMenu, setContextMenu] = useState({ show: false, x: 0, y: 0, targetNode: null });
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [userPermissions, setUserPermissions] = useState({});
    const [isDisableTempModalOpen, setIsDisableTempModalOpen] = useState(false);
    const [isScheduleAbsenceModalOpen, setIsScheduleAbsenceModalOpen] = useState(false);
    const [actionUser, setActionUser] = useState(null);
    const [isMoveModalOpenFromContext, setIsMoveModalOpenFromContext] = useState(false);
    const [objectToMove, setObjectToMove] = useState(null);
    const [notification, setNotification] = useState({ isOpen: false, title: '', message: '' });

    useEffect(() => {
        axios.get('/api/action_permissions')
            .then(response => setUserPermissions(response.data))
            .catch(error => console.error("Erro ao buscar permissões:", error));
    }, []);

    const handleRestore = (node) => {
        setConfirmationAction({
            isOpen: true,
            title: 'Restaurar Objeto',
            message: `Tem certeza que deseja restaurar o objeto "${node.name}"?`,
            onConfirm: () => {
                axios.post('/api/restore_object', { dn: node.dn })
                    .then(response => {
                        setNotification({ isOpen: true, title: 'Sucesso', message: response.data.message });
                        setMembers(prev => prev.filter(m => m.dn !== node.dn));
                    })
                    .catch(error => setNotification({ isOpen: true, title: 'Erro', message: error.response?.data?.error || 'Erro desconhecido' }))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleEdit = (node) => {
        if (node.type === 'user' && node.sam) {
            setEditingUser(node.sam);
            setIsEditModalOpen(true);
        }
    };

    const handleToggleStatus = (node) => {
        const actionText = node.status === 'Ativo' ? 'Desativar' : 'Ativar';
        setConfirmationAction({
            isOpen: true,
            title: `${actionText} Conta`,
            message: `Tem certeza que deseja ${actionText.toLowerCase()} a conta de ${node.name}?`,
            onConfirm: () => {
                axios.post('/api/toggle_object_status', { dn: node.dn, sam: node.sam })
                    .then(response => {
                        setNotification({ isOpen: true, title: 'Sucesso', message: response.data.message });
                    })
                    .catch(error => setNotification({ isOpen: true, title: 'Erro', message: error.response?.data?.error || 'Erro desconhecido' }))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleResetPassword = (node) => {
        setConfirmationAction({
            isOpen: true,
            title: 'Resetar Senha',
            message: `Tem certeza que deseja resetar a senha de ${node.name}? Uma nova senha padrão será definida.`,
            onConfirm: () => {
                axios.post(`/api/reset_password/${node.sam}`)
                    .then(response => {
                        setNotification({ isOpen: true, title: 'Sucesso', message: `${response.data.message} Nova senha: ${response.data.new_password}` });
                    })
                    .catch(error => setNotification({ isOpen: true, title: 'Erro', message: error.response?.data?.error || 'Erro desconhecido' }))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleDelete = (node) => {
        setConfirmationAction({
            isOpen: true,
            title: 'Excluir Objeto',
            message: `Atenção! Tem certeza que deseja excluir permanentemente ${node.name}? Esta ação não pode ser desfeita.`,
            onConfirm: () => {
                axios.delete('/api/delete_object', { data: { dn: node.dn, name: node.name } })
                    .then(response => {
                        setNotification({ isOpen: true, title: 'Sucesso', message: response.data.message });
                        setMembers(prev => prev.filter(m => m.dn !== node.dn));
                        setSearchResults(prev => prev.filter(r => r.dn !== node.dn));
                    })
                    .catch(error => setNotification({ isOpen: true, title: 'Erro', message: error.response?.data?.error || 'Erro desconhecido' }))
                    .finally(() => setConfirmationAction({ isOpen: false }));
            }
        });
    };

    const handleDisableTemp = (node) => {
        if (node.type === 'user' && node.sam) {
            setActionUser(node.sam);
            setIsDisableTempModalOpen(true);
        }
    };

    const handleScheduleAbsence = (node) => {
        if (node.type === 'user' && node.sam) {
            setActionUser(node.sam);
            setIsScheduleAbsenceModalOpen(true);
        }
    };

    const handleMove = (node) => {
        setObjectToMove(node);
        setIsMoveModalOpenFromContext(true);
    };

    const handleContextMenu = (e, node) => {
        e.preventDefault();
        e.stopPropagation();
        setContextMenu({
            show: true,
            x: e.clientX,
            y: e.clientY,
            targetNode: node
        });
    };

    const handleOuDoubleClick = (ouMember) => {
        let targetNode = null;
        const findNodeRecursive = (nodes, dn) => {
            for (const node of nodes) {
                if (node.dn === dn) {
                    targetNode = node;
                    return;
                }
                if (node.nodes) findNodeRecursive(node.nodes, dn);
                if (targetNode) return;
            }
        };
        findNodeRecursive(treeData, ouMember.dn);

        if (targetNode) handleNodeClick(targetNode, true);
    };

    const findAndUpdateNode = useCallback((nodes, dn, updateCallback) => {
        return nodes.map(node => {
            if (node.dn === dn) {
                return updateCallback(node);
            }
            if (node.nodes) {
                return { ...node, nodes: findAndUpdateNode(node.nodes, dn, updateCallback) };
            }
            return node;
        });
    }, []);

    const handleNodeClick = useCallback((node, isOpen) => {
        setSelectedNode(node);
        setSearchPerformed(false);
        setSearchQuery('');

        const apiUrl = node.dn === 'recycle_bin'
            ? '/api/recycle_bin'
            : `/api/ou_members/${encodeURIComponent(node.dn)}`;

        axios.get(apiUrl)
            .then(response => {
                setMembers(response.data);
                if (isOpen && node.dn !== 'recycle_bin' && (!node.nodes || node.nodes.length === 0)) {
                    const ouChildren = response.data.filter(m => m.type === 'ou');
                    setTreeData(prevTree => findAndUpdateNode(prevTree, node.dn, n => ({ ...n, nodes: ouChildren })));
                }
            })
            .catch(error => console.error(`Erro ao buscar membros para ${node.text}:`, error));
    }, [findAndUpdateNode]);

    const handleMoveObject = useCallback((item, targetNode) => {
        const sourceOuDn = item.dn.substring(item.dn.indexOf(',') + 1);
        if (sourceOuDn === targetNode.dn) return;

        setMoveDetails({ item, targetNode, sourceOuDn });
        setIsMoveModalOpen(true);
    }, []);

    const confirmMove = () => {
        if (!moveDetails) return;
        const { item, targetNode, sourceOuDn } = moveDetails;

        axios.post('/api/move_object', {
            object_dn: item.dn,
            target_ou_dn: targetNode.dn,
        })
        .then(response => {
            if (response.data.success) {
                setNotification({ isOpen: true, title: 'Sucesso', message: 'Objeto movido com sucesso!' });
                if (selectedNode && selectedNode.dn === sourceOuDn) {
                    setMembers(prevMembers => prevMembers.filter(m => m.dn !== item.dn));
                }
                if (selectedNode && selectedNode.dn === targetNode.dn) {
                    const newDn = `${item.dn.split(',')[0]},${targetNode.dn}`;
                    const movedItem = { ...item, dn: newDn };
                    setMembers(prevMembers => [...prevMembers, movedItem].sort((a, b) => a.name.localeCompare(b.name)));
                }
            } else {
                setNotification({ isOpen: true, title: 'Erro', message: `Falha ao mover o objeto: ${response.data.error || 'Erro desconhecido.'}` });
            }
        })
        .catch(error => {
            const errorMessage = error.response?.data?.error || 'Ocorreu um erro de comunicação.';
            setNotification({ isOpen: true, title: 'Erro', message: errorMessage });
        })
        .finally(() => {
            setIsMoveModalOpen(false);
            setMoveDetails(null);
        });
    };

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        if (searchQuery.trim().length < 3) {
            setNotification({ isOpen: true, title: 'Atenção', message: 'A busca deve ter no mínimo 3 caracteres.' });
            return;
        }
        setIsSearchLoading(true);
        setSearchPerformed(true);
        setSelectedNode(null);
        setMembers([]);
        axios.get(`/api/search_ad?q=${encodeURIComponent(searchQuery)}`)
            .then(response => {
                setSearchResults(response.data);
            })
            .catch(error => {
                console.error("Erro na busca:", error);
                const errorMessage = error.response?.data?.error || 'Ocorreu um erro ao realizar a busca.';
                setNotification({ isOpen: true, title: 'Erro na Busca', message: errorMessage });
                setSearchResults([]);
            })
            .finally(() => {
                setIsSearchLoading(false);
            });
    };

    const clearSearch = () => {
        setSearchQuery('');
        setSearchResults([]);
        setSearchPerformed(false);
        setSelectedNode(null);
        setMembers([]);
    };

    useEffect(() => {
        axios.get('/api/ous')
          .then(response => setTreeData(response.data))
          .catch(error => console.error("Error fetching OUs:", error));
    }, []);

    const getIcon = (type, isDeleted = false) => {
        if (isDeleted) return <i className="fas fa-trash-restore me-2"></i>;
        switch (type) {
            case 'ou': return <i className="fas fa-folder me-2"></i>;
            case 'user': return <i className="fas fa-user me-2"></i>;
            case 'group': return <i className="fas fa-users me-2"></i>;
            case 'computer': return <i className="fas fa-desktop me-2"></i>;
            default: return <i className="fas fa-file me-2"></i>;
        }
    };

    return (
        <DndProvider backend={HTML5Backend}>
            <div className="ad-explorer-container" onClick={() => setContextMenu({ ...contextMenu, show: false })}>
                <div className="panels-container">
                    <div className="tree-panel">
                        <div className="search-container">
                            <form onSubmit={handleSearchSubmit} className="search-form">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="Buscar usuário ou computador..."
                                    className="search-input"
                                />
                                <button type="submit" className="search-button" disabled={isSearchLoading}>
                                    {isSearchLoading ? <i className="fas fa-spinner fa-spin"></i> : <i className="fas fa-search"></i>}
                                </button>
                                {searchPerformed && (
                                    <button type="button" onClick={clearSearch} className="clear-button">
                                        <i className="fas fa-times"></i>
                                    </button>
                                )}
                            </form>
                        </div>
                        {treeData.map(rootNode => (
                            <TreeNode key={rootNode.dn} node={rootNode} onNodeClick={handleNodeClick} onMoveObject={handleMoveObject} onContextMenu={handleContextMenu} />
                        ))}
                    </div>
                    <ContentPanel
                        selectedNode={selectedNode}
                        members={searchPerformed ? searchResults : members}
                        getIcon={getIcon}
                        onOuDoubleClick={handleOuDoubleClick}
                        isSearchMode={searchPerformed}
                        onContextMenu={handleContextMenu}
                    />
                </div>
                <ConfirmationModal
                    isOpen={isMoveModalOpen}
                    onClose={() => setIsMoveModalOpen(false)}
                    onConfirm={confirmMove}
                    title="Confirmar Movimentação"
                >
                    {moveDetails && (
                        <p>
                            Tem certeza que deseja mover <strong>{moveDetails.item.name}</strong> para a Unidade Organizacional <strong>{moveDetails.targetNode.text}</strong>?
                        </p>
                    )}
                </ConfirmationModal>
                <ConfirmationModal
                    isOpen={confirmationAction.isOpen}
                    onClose={() => setConfirmationAction({ isOpen: false })}
                    onConfirm={confirmationAction.onConfirm}
                    title={confirmationAction.title}
                >
                    <p>{confirmationAction.message}</p>
                </ConfirmationModal>
                <ContextMenu
                    x={contextMenu.x}
                    y={contextMenu.y}
                    show={contextMenu.show}
                    targetNode={contextMenu.targetNode}
                    onClose={() => setContextMenu({ ...contextMenu, show: false })}
                    permissions={userPermissions}
                    onEdit={handleEdit}
                    onToggleStatus={handleToggleStatus}
                    onResetPassword={handleResetPassword}
                    onDelete={handleDelete}
                    onDisableTemp={handleDisableTemp}
                    onScheduleAbsence={handleScheduleAbsence}
                    onMove={handleMove}
                    onRestore={handleRestore}
                />
                <EditUserModal isOpen={isEditModalOpen} onClose={() => setIsEditModalOpen(false)} username={editingUser} />
                <DisableTempModal isOpen={isDisableTempModalOpen} onClose={() => setIsDisableTempModalOpen(false)} username={actionUser} />
                <ScheduleAbsenceModal isOpen={isScheduleAbsenceModalOpen} onClose={() => setIsScheduleAbsenceModalOpen(false)} username={actionUser} />
                <MoveModal
                    isOpen={isMoveModalOpenFromContext}
                    onClose={() => setIsMoveModalOpenFromContext(false)}
                    objectToMove={objectToMove}
                    onConfirmMove={(targetOu) => {
                        if (!objectToMove || !targetOu) return;

                        axios.post('/api/move_object', {
                            object_dn: objectToMove.dn,
                            target_ou_dn: targetOu.dn,
                        })
                        .then(response => {
                            if (response.data.success) {
                                setNotification({ isOpen: true, title: 'Sucesso', message: 'Objeto movido com sucesso!' });
                                setMembers(prev => prev.filter(m => m.dn !== objectToMove.dn));
                                setSearchResults(prev => prev.filter(r => r.dn !== objectToMove.dn));
                            } else {
                                setNotification({ isOpen: true, title: 'Erro', message: `Falha ao mover: ${response.data.error}` });
                            }
                        })
                        .catch(err => {
                            setNotification({ isOpen: true, title: 'Erro', message: `Erro na comunicação: ${err.response?.data?.error || 'Erro desconhecido'}` });
                        })
                        .finally(() => {
                            setIsMoveModalOpenFromContext(false);
                            setObjectToMove(null);
                        });
                    }}
                />
                <NotificationModal
                    isOpen={notification.isOpen}
                    onClose={() => setNotification({ ...notification, isOpen: false })}
                    title={notification.title}
                    message={notification.message}
                />
            </div>
        </DndProvider>
    );
};

export default ADExplorerPage;
