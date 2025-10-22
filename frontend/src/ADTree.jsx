import React, { useState, useEffect } from 'react';
import axios from 'axios';

const TreeNode = ({ node }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [children, setChildren] = useState([]);

  const toggleOpen = () => {
    setIsOpen(!isOpen);
    if (!isOpen && children.length === 0) {
      // Fetch children if not already fetched
      axios.get(`/api/ou_members/${encodeURIComponent(node.dn)}`)
        .then(response => {
          setChildren(response.data);
        })
        .catch(error => {
          console.error("Error fetching OU members:", error);
        });
    }
  };

  const getIcon = (type) => {
    switch (type) {
        case 'ou':
            return <i className="bi bi-folder"></i>;
        case 'user':
            return <i className="bi bi-person"></i>;
        case 'group':
            return <i className="bi bi-people"></i>;
        default:
            return null;
    }
  };


  return (
    <div style={{ marginLeft: '20px' }}>
      <div onClick={toggleOpen} style={{ cursor: 'pointer' }}>
        {getIcon(node.type)} {node.text || node.name}
      </div>
      {isOpen && (
        <div>
          {children.map(child => (
            <TreeNode key={child.dn} node={child} />
          ))}
        </div>
      )}
    </div>
  );
};

const ADTree = () => {
  const [treeData, setTreeData] = useState([]);

  useEffect(() => {
    axios.get('/api/ous')
      .then(response => {
        setTreeData(response.data);
      })
      .catch(error => {
        console.error("Error fetching OUs:", error);
      });
  }, []);

  return (
    <div>
      <h1>Active Directory Tree</h1>
      {treeData.map(rootNode => (
        <TreeNode key={rootNode.dn} node={{...rootNode, type: 'ou'}} />
      ))}
    </div>
  );
};

export default ADTree;