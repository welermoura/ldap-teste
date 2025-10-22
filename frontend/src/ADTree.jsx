import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './ADTree.css'; // New CSS file for styling

// Panel to display the contents of the selected OU
const ContentPanel = ({ selectedNode, members }) => {
    if (!selectedNode) {
        return (
            <div className="content-panel">
                <div className="content-placeholder">
                    Selecione uma Unidade Organizacional na árvore para ver seu conteúdo.
                </div>
            </div>
        );
    }

    const getIcon = (type) => {
        switch (type) {
            case 'ou':
                return <i className="fas fa-folder"></i>;
            case 'user':
                return <i className="fas fa-user"></i>;
            case 'group':
                return <i className="fas fa-users"></i>;
            default:
                return <i className="fas fa-file"></i>;
        }
    };

    return (
        <div className="content-panel">
            <h4 className="content-header">Conteúdo de: {selectedNode.text || selectedNode.name}</h4>
            <ul className="member-list">
                {members.map(member => (
                    <li key={member.dn} className="member-item">
                        {getIcon(member.type)}
                        <span className="member-name">{member.name}</span>
                    </li>
                ))}
            </ul>
        </div>
    );
};


// The actual tree node component
const TreeNode = ({ node, onNodeClick }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [children, setChildren] = useState([]);

  const handleNodeClick = () => {
    // When a node is clicked, we toggle it AND notify the parent
    toggleOpen();
    onNodeClick(node, children); // Pass the node and its current children
  };

  const toggleOpen = () => {
    setIsOpen(!isOpen);
    // If we're opening it and haven't fetched children yet
    if (!isOpen && children.length === 0 && node.type === 'ou') {
      axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
        .then(response => {
          const allMembers = response.data;
          const ouChildren = allMembers.filter(member => member.type === 'ou');
          setChildren(ouChildren);
          // Pass all members to the content panel, but only OUs to the tree
          onNodeClick(node, allMembers);
        })
        .catch(error => {
          console.error("Error fetching OU members:", error);
        });
    } else {
        // We need to refetch to get the full list for the panel
        axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
            .then(response => {
                onNodeClick(node, response.data);
            });
    }
  };

  const getIcon = (type) => {
    switch (type) {
        case 'ou':
            return <i className="fas fa-folder"></i>;
        case 'user':
            return <i className="fas fa-user"></i>;
        case 'group':
            return <i className="fas fa-users"></i>;
        default:
            return <i className="fas fa-file"></i>; // Fallback icon
    }
  };

  return (
    <div className="tree-node">
      <div onClick={handleNodeClick} className="node-label">
        {getIcon(node.type)} {node.text || node.name}
      </div>
      {isOpen && (
        <div className="node-children">
          {children.map(child => (
            <TreeNode key={child.dn} node={child} onNodeClick={onNodeClick} />
          ))}
        </div>
      )}
    </div>
  );
};

// Main page component that orchestrates the layout
const ADExplorerPage = () => {
  const [treeData, setTreeData] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [members, setMembers] = useState([]);

  // Fetch the root OUs when the component mounts
  useEffect(() => {
    axios.get('/api/ous')
      .then(response => {
        setTreeData(response.data);
      })
      .catch(error => {
        console.error("Error fetching OUs:", error);
      });
  }, []);

  // This function will be called by any TreeNode when it's clicked
  const handleNodeSelection = (node, children) => {
      setSelectedNode(node);
      setMembers(children);
  };

  return (
    <div className="ad-explorer-container">
        <h1 className="main-header">Explorador do Active Directory</h1>
        <div className="panels-container">
            <div className="tree-panel">
                {treeData.map(rootNode => (
                    <TreeNode key={rootNode.dn} node={{...rootNode, type: 'ou'}} onNodeClick={handleNodeSelection} />
                ))}
            </div>
            <ContentPanel selectedNode={selectedNode} members={members} />
        </div>
    </div>
  );
};

export default ADExplorerPage;
