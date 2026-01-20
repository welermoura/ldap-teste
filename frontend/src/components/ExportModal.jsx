import React, { useState } from 'react';
import { Download, FileText, Monitor, X, CheckCircle, Loader2 } from 'lucide-react';
import { pdf } from '@react-pdf/renderer';
import { saveAs } from 'file-saver';
import { generatePPTX } from '../services/pptxGenerator';
import OrganogramDocument from '../services/pdfDocument';
import { filterTree } from '../utils/exportUtils';

const ExportModal = ({ isOpen, onClose, data, selectedNodeId }) => {
    const [format, setFormat] = useState('pdf'); // 'pdf' | 'pptx'
    const [scope, setScope] = useState('full'); // 'full' | 'subtree' | 'single'
    const [loading, setLoading] = useState(false);
    const [success, setSuccess] = useState(false);

    if (!isOpen) return null;

    const handleExport = async () => {
        setLoading(true);
        setSuccess(false);

        try {
            // 1. Filtrar dados
            const filteredData = filterTree(data, scope, selectedNodeId);

            if (filteredData.length === 0) {
                alert('Nenhum dado encontrado para o escopo selecionado.');
                setLoading(false);
                return;
            }

            // 2. Gerar arquivo
            if (format === 'pptx') {
                await generatePPTX(filteredData, scope);
            } else {
                const blob = await pdf(<OrganogramDocument data={filteredData} scope={scope} />).toBlob();
                saveAs(blob, `Organograma_${scope}.pdf`);
            }

            setSuccess(true);
            setTimeout(() => {
                setSuccess(false);
                onClose();
            }, 1500);
        } catch (error) {
            console.error('Export error:', error);
            alert('Erro na exportação. Verifique o console.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="modal-overlay">
            <div className="modal-content">
                <div className="modal-header">
                    <h3>Exportar Organograma</h3>
                    <button className="close-btn" onClick={onClose}><X size={20} /></button>
                </div>

                <div className="modal-body">
                    {/* Seleção de Formato */}
                    <div className="section">
                        <label>Formato</label>
                        <div className="options-grid">
                            <button
                                className={`option-card ${format === 'pdf' ? 'selected' : ''}`}
                                onClick={() => setFormat('pdf')}
                            >
                                <FileText size={24} />
                                <span>PDF</span>
                            </button>
                            <button
                                className={`option-card ${format === 'pptx' ? 'selected' : ''}`}
                                onClick={() => setFormat('pptx')}
                            >
                                <Monitor size={24} />
                                <span>PowerPoint</span>
                            </button>
                        </div>
                    </div>

                    {/* Seleção de Escopo */}
                    <div className="section">
                        <label>Escopo</label>
                        <div className="radio-group">
                            <label className="radio-item">
                                <input
                                    type="radio"
                                    name="scope"
                                    value="full"
                                    checked={scope === 'full'}
                                    onChange={(e) => setScope(e.target.value)}
                                />
                                <div className="radio-info">
                                    <span className="radio-title">Organização Inteira</span>
                                    <span className="radio-desc">Exportar todos os níveis disponíveis.</span>
                                </div>
                            </label>

                            <label className={`radio-item ${!selectedNodeId ? 'disabled' : ''}`}>
                                <input
                                    type="radio"
                                    name="scope"
                                    value="subtree"
                                    checked={scope === 'subtree'}
                                    onChange={(e) => setScope(e.target.value)}
                                    disabled={!selectedNodeId}
                                />
                                <div className="radio-info">
                                    <span className="radio-title">Nó Selecionado + Subordinados</span>
                                    <span className="radio-desc">
                                        {selectedNodeId ? 'Apenas a área focada e seus níveis abaixo.' : 'Selecione um nó primeiro.'}
                                    </span>
                                </div>
                            </label>

                            <label className={`radio-item ${!selectedNodeId ? 'disabled' : ''}`}>
                                <input
                                    type="radio"
                                    name="scope"
                                    value="single"
                                    checked={scope === 'single'}
                                    onChange={(e) => setScope(e.target.value)}
                                    disabled={!selectedNodeId}
                                />
                                <div className="radio-info">
                                    <span className="radio-title">Apenas Nó Selecionado</span>
                                    <span className="radio-desc">Somente o card focado (sem filhos).</span>
                                </div>
                            </label>
                        </div>
                    </div>
                </div>

                <div className="modal-footer">
                    <button className="btn-cancel" onClick={onClose} disabled={loading}>Cancelar</button>
                    <button className="btn-export" onClick={handleExport} disabled={loading}>
                        {loading ? <Loader2 className="spinner" size={18} /> : success ? <CheckCircle size={18} /> : <Download size={18} />}
                        {loading ? 'Gerando...' : success ? 'Sucesso!' : 'Exportar'}
                    </button>
                </div>
            </div>

            <style>{`
                .modal-overlay {
                    position: fixed;
                    top: 0; left: 0; right: 0; bottom: 0;
                    background: rgba(0, 0, 0, 0.5);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 1000;
                    backdrop-filter: blur(4px);
                }
                .modal-content {
                    background: #fff;
                    width: 480px;
                    border-radius: 12px;
                    box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1);
                    overflow: hidden;
                    font-family: 'Inter', sans-serif;
                }
                .modal-header {
                    padding: 16px 24px;
                    border-bottom: 1px solid #e2e8f0;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .modal-header h3 { margin: 0; font-size: 1.1rem; color: #0f172a; }
                .close-btn {
                    background: none; border: none; cursor: pointer; color: #64748b;
                }
                .modal-body {
                    padding: 24px;
                }
                .section {
                    margin-bottom: 24px;
                }
                .section label {
                    display: block;
                    font-size: 0.85rem;
                    font-weight: 600;
                    color: #475569;
                    margin-bottom: 12px;
                    text-transform: uppercase;
                    letter-spacing: 0.05em;
                }
                .options-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 12px;
                }
                .option-card {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 8px;
                    padding: 16px;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    background: #f8fafc;
                    cursor: pointer;
                    transition: all 0.2s;
                    color: #64748b;
                }
                .option-card:hover { border-color: #cbd5e1; background: #fff; }
                .option-card.selected {
                    border-color: #3b82f6;
                    background: #eff6ff;
                    color: #3b82f6;
                    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
                }
                .radio-group {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
                .radio-item {
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    padding: 12px;
                    border: 1px solid #e2e8f0;
                    border-radius: 8px;
                    cursor: pointer;
                    transition: background 0.2s;
                }
                .radio-item:hover:not(.disabled) { background: #f8fafc; }
                .radio-item.disabled { opacity: 0.5; cursor: not-allowed; }
                .radio-item input { margin-top: 4px; accent-color: #3b82f6; }
                .radio-info { display: flex; flex-direction: column; }
                .radio-title { font-size: 0.9rem; font-weight: 500; color: #0f172a; }
                .radio-desc { font-size: 0.8rem; color: #64748b; }

                .modal-footer {
                    padding: 16px 24px;
                    background: #f8fafc;
                    border-top: 1px solid #e2e8f0;
                    display: flex;
                    justify-content: flex-end;
                    gap: 12px;
                }
                .btn-cancel {
                    padding: 8px 16px;
                    border: 1px solid #cbd5e1;
                    border-radius: 6px;
                    background: #fff;
                    color: #475569;
                    cursor: pointer;
                    font-weight: 500;
                }
                .btn-export {
                    padding: 8px 20px;
                    background: #0f172a;
                    color: #fff;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-weight: 500;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    transition: background 0.2s;
                }
                .btn-export:hover:not(:disabled) { background: #1e293b; }
                .btn-export:disabled { opacity: 0.7; cursor: wait; }
                .spinner { animation: spin 1s linear infinite; }
                @keyframes spin { to { transform: rotate(360deg); } }
            `}</style>
        </div>
    );
};

export default ExportModal;
