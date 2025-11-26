import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import TreeNode from './TreeNode';
import '../styles/MoveModal.css';

const MoveModal = ({ isOpen, onClose, onConfirmMove, objectToMove }) => {
    const [treeData, setTreeData] = useState([]);
    const [selectedOu, setSelectedOu] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const findAndSetNodeProp = useCallback((nodes, dn, prop, value) => {
        return nodes.map(node => {
            const newNode = { ...node, [prop]: node.dn === dn ? value : false };
            if (node.nodes) {
                newNode.nodes = findAndSetNodeProp(node.nodes, dn, prop, value);
            }
            return newNode;
        });
    }, []);

    const handleNodeClickInModal = (node) => {
        setSelectedOu(node);
        // Destaca o nó selecionado
        setTreeData(prevTree => findAndSetNodeProp(prevTree, node.dn, 'isSelected', true));
    };

    useEffect(() => {
        if (isOpen) {
            setIsLoading(true);
            setError('');
            setSelectedOu(null);
            axios.get('/api/ous')
                .then(response => setTreeData(response.data))
                .catch(() => setError('Não foi possível carregar a estrutura de OUs.'))
                .finally(() => setIsLoading(false));
        }
    }, [isOpen]);

    const handleConfirm = () => {
        if (selectedOu) {
            onConfirmMove(selectedOu);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="modal-backdrop">
            <div className="modal-content move-modal">
                <div className="modal-header">
                    <h5 className="modal-title">Mover "{objectToMove?.name}"</h5>
                    <button type="button" className="btn-close" onClick={onClose}></button>
                </div>
                <div className="modal-body">
                    {isLoading && <p>Carregando árvore...</p>}
                    {error && <div className="alert alert-danger">{error}</div>}
                    <p>Selecione a Unidade Organizacional de destino:</p>
                    <div className="tree-container-modal">
                        {treeData.map(rootNode => (
                            <TreeNode
                                key={rootNode.dn}
                                node={rootNode}
                                onNodeClick={handleNodeClickInModal}
                                // Passa null para onMoveObject para desativar o drop
                                onMoveObject={null}
                                onContextMenu={null}
                            />
                        ))}
                    </div>
                </div>
                <div className="modal-footer">
                    <button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
                    <button
                        type="button"
                        className="btn btn-primary"
                        onClick={handleConfirm}
                        disabled={!selectedOu}
                    >
                        Confirmar Movimentação
                    </button>
                </div>
            </div>
        </div>
    );
};

export default MoveModal;
