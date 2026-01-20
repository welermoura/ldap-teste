import React from 'react';
import { Page, Text, View, Document, StyleSheet } from '@react-pdf/renderer';
import { buildMatrixLayout } from './layoutMatrixBuilder';

const styles = StyleSheet.create({
    page: {
        flexDirection: 'column',
        backgroundColor: '#FFFFFF',
        padding: 30,
    },
    header: {
        marginBottom: 15,
        borderBottomWidth: 1,
        borderBottomColor: '#E2E8F0',
        paddingBottom: 8,
    },
    title: {
        fontSize: 18,
        color: '#1E293B',
        marginBottom: 2,
    },
    subtitle: {
        fontSize: 10,
        color: '#64748B',
    },
    contentContainer: {
        flex: 1,
        justifyContent: 'flex-start', // Top aligned usually better for levels
        paddingTop: 10,
    },
    rowContainer: {
        flexDirection: 'row',
        justifyContent: 'center', // Center content horizontally
        marginBottom: 20, // Space between levels
        gap: 15,
    },
    card: {
        width: 120,
        height: 60,
        padding: 8,
        backgroundColor: '#FFFFFF',
        borderWidth: 1,
        borderColor: '#E2E8F0',
        borderRadius: 4,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cardName: {
        fontSize: 9,
        fontWeight: 'bold',
        color: '#0F172A',
        textAlign: 'center',
        marginBottom: 2,
    },
    cardRole: {
        fontSize: 7,
        color: '#475569',
        textAlign: 'center',
    },
    footer: {
        position: 'absolute',
        bottom: 20,
        right: 30,
        fontSize: 8,
        color: '#94A3B8',
    }
});

const OrganogramDocument = ({ data, scope }) => {
    // Escopo já foi filtrado no Modal, aqui recebemos a subárvore pronta
    const pages = buildMatrixLayout(data);

    return (
        <Document>
            {pages.map((pageData, index) => (
                <Page key={index} size="A4" orientation="landscape" style={styles.page}>
                    <View style={styles.header}>
                        <Text style={styles.title}>{pageData.title}</Text>
                        <Text style={styles.subtitle}>{pageData.subtitle}</Text>
                    </View>

                    <View style={styles.contentContainer}>
                        {pageData.rows.map((row, rowIdx) => (
                            <View key={rowIdx} style={styles.rowContainer}>
                                {row.items.map((item, itemIdx) => (
                                    <View key={itemIdx} style={styles.card}>
                                        <Text style={styles.cardName}>{item.name}</Text>
                                        <Text style={styles.cardRole}>{item.title}</Text>
                                        <Text style={{ fontSize: 6, color: '#94A3B8', marginTop: 2 }}>{item.department}</Text>
                                    </View>
                                ))}
                            </View>
                        ))}
                    </View>

                    <Text style={styles.footer} render={({ pageNumber, totalPages }) => (
                        `${pageNumber} / ${totalPages}`
                    )} fixed />
                </Page>
            ))}
        </Document>
    );
};

export default OrganogramDocument;
