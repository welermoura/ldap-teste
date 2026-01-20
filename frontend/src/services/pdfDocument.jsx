import React from 'react';
import { Page, Text, View, Document, StyleSheet, Font } from '@react-pdf/renderer';
import { flattenTree } from '../utils/exportUtils';

// Fontes padrão (Helvetica é built-in, mas podemos registrar custom se necessário)
const styles = StyleSheet.create({
    page: {
        flexDirection: 'column',
        backgroundColor: '#FFFFFF',
        padding: 30,
    },
    header: {
        marginBottom: 20,
        borderBottomWidth: 1,
        borderBottomColor: '#E2E8F0',
        paddingBottom: 10,
    },
    title: {
        fontSize: 24,
        color: '#1E293B',
        marginBottom: 4,
    },
    subtitle: {
        fontSize: 12,
        color: '#64748B',
    },
    section: {
        margin: 10,
        padding: 10,
        flexGrow: 1,
    },
    nodeRow: {
        flexDirection: 'row',
        marginBottom: 8,
        alignItems: 'center',
    },
    connector: {
        width: 15,
        height: 1,
        backgroundColor: '#CBD5E1',
        marginRight: 5,
    },
    card: {
        borderWidth: 1,
        borderColor: '#E2E8F0',
        borderRadius: 4,
        padding: 8,
        flexGrow: 1,
        backgroundColor: '#F8FAFC',
    },
    name: {
        fontSize: 12,
        fontWeight: 'bold',
        color: '#0F172A',
    },
    role: {
        fontSize: 10,
        color: '#475569',
    }
});

const OrganogramDocument = ({ data, scope }) => {
    const flatData = flattenTree(data);

    return (
        <Document>
            <Page size="A4" style={styles.page}>
                <View style={styles.header}>
                    <Text style={styles.title}>Organograma Corporativo</Text>
                    <Text style={styles.subtitle}>
                        {scope === 'full' ? 'Visão Completa' : 'Visão Parcial'} • Gerado em {new Date().toLocaleDateString()}
                    </Text>
                </View>

                <View>
                    {flatData.map((node, index) => (
                        <View key={index} style={{
                            ...styles.nodeRow,
                            marginLeft: node.depth * 20, // Indentação visual
                            marginTop: index === 0 ? 0 : 4
                        }}>
                            {node.depth > 0 && <View style={styles.connector} />}
                            <View style={styles.card}>
                                <Text style={styles.name}>{node.name}</Text>
                                <Text style={styles.role}>
                                    {node.title || 'Cargo N/A'} • {node.department || 'Depto N/A'}
                                </Text>
                            </View>
                        </View>
                    ))}
                </View>

                <Text style={{ position: 'absolute', bottom: 30, right: 30, fontSize: 10, color: '#94A3B8' }} render={({ pageNumber, totalPages }) => (
                    `${pageNumber} / ${totalPages}`
                )} fixed />
            </Page>
        </Document>
    );
};

export default OrganogramDocument;
