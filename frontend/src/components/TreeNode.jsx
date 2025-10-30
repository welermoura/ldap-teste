import React, { useState, useEffect } from 'react';
import { useDrop } from 'react-dnd';
import { ItemTypes } from './dndTypes'; // Importar de arquivo separado

// O componente de nó da árvore, agora em seu próprio arquivo
const TreeNode = ({ node, onNodeClick, onMoveObject, onContextMenu }) => {
    const [isOpen, setIsOpen] = useState(false);
    const children = node.nodes || [];

    const [{ isOver, canDrop }, drop] = useDrop(() => ({
        accept: ItemTypes.AD_OBJECT,
        drop: (item) => {
            if (onMoveObject) {
                onMoveObject(item, node);
            }
        },
        canDrop: (item) => item.type !== 'ou',
        collect: (monitor) => ({
            isOver: !!monitor.isOver({ shallow: true }),
            canDrop: !!monitor.canDrop(),
        }),
    }), [node, onMoveObject]);

    useEffect(() => {
        let timer = null;
        if (isOver && canDrop && !isOpen) {
            timer = setTimeout(() => {
                setIsOpen(true);
                if (onNodeClick) {
                    onNodeClick(node, true);
                }
            }, 500);
        }
        return () => {
            if (timer) {
                clearTimeout(timer);
            }
        };
    }, [isOver, canDrop, isOpen, onNodeClick, node]);

    const handleNodeClick = () => {
        setIsOpen(!isOpen);
        if (onNodeClick) {
            onNodeClick(node, !isOpen);
        }
    };

    const getIcon = (node) => {
        if (node.icon) {
            return <i className={node.icon}></i>;
        }
        // O tipo 'ou' é implícito para todos os nós da árvore, então o ícone padrão é a pasta
        return <i className="fas fa-folder"></i>;
    };

    // Adiciona a classe 'selected' se o nó estiver selecionado
    const isSelected = node.isSelected;

    return (
        <div ref={onMoveObject ? drop : null} className={`tree-node ${isOver && canDrop ? 'drop-target-highlight' : ''}`}>
            <div
                onClick={handleNodeClick}
                className={`node-label ${isSelected ? 'selected' : ''}`}
                onContextMenu={onContextMenu ? (e) => onContextMenu(e, node) : null}
            >
                {getIcon(node)} {node.text}
            </div>
            {isOpen && (
                <div className="node-children">
                    {children.map(child => (
                        <TreeNode
                            key={child.dn}
                            node={child}
                            onNodeClick={onNodeClick}
                            onMoveObject={onMoveObject}
                            onContextMenu={onContextMenu}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default TreeNode;
