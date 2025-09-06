#!/usr/bin/env python3
"""
Streamlit version of Schedulean - A cloud-based P6 Schedule Analyzer

This converts the tkinter-based Schedulean app to run as a web application
using Streamlit, allowing deployment on Streamlit Community Cloud for free.

Features:
- Upload multiple P6 XER/XML files
- Activity and relationship analysis
- Cost metrics breakdown (Labor, Non-Labor, Material)
- Resource assignment analysis
- Redundant logic detection
- Data export functionality
"""

import streamlit as st
import pandas as pd
import io
from datetime import datetime
from collections import defaultdict, deque
import sys
import os

# Constants from original Schedulean.py
XER_ACTIVITY_MAP = {
    'TT_Task': 'Task Dependent',
    'TT_Rsrc': 'Resource Dependent', 
    'TT_LOE': 'Level of Effort',
    'TT_Mile': 'Start Milestone',
    'TT_FinMile': 'Finish Milestone',
    'TT_WBS': 'WBS Summary'
}

XER_REL_MAP = {
    'PR_FS': 'Finish-to-Start (FS)',
    'PR_FF': 'Finish-to-Finish (FF)', 
    'PR_SS': 'Start-to-Start (SS)',
    'PR_SF': 'Start-to-Finish (SF)'
}

# Helper functions (copied from original Schedulean.py)
def safe_float(value, default=0.0):
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_field_value(data_row, keys):
    """
    Extract a field value from a data row (dict) using a list of possible keys.
    Returns the first non-empty value found, or None if all keys are missing/empty.
    """
    for key in keys:
        val = data_row.get(key, '').strip()
        if val:
            return val
    return None

def analyze_redundant_logic(activities, relationships):
    """Detect redundant relationships in the project schedule."""
    try:
        # Build adjacency list representation
        graph = defaultdict(list)
        rel_map = {}
        
        for rel in relationships:
            pred_id = rel.get('pred_task_id', '')
            succ_id = rel.get('succ_task_id', '')
            rel_type = rel.get('pred_type', 'PR_FS')
            lag = safe_float(rel.get('lag_hr_cnt', 0))
            
            if pred_id and succ_id:
                graph[pred_id].append((succ_id, rel_type, lag))
                rel_key = (pred_id, succ_id, rel_type)
                rel_map[rel_key] = rel
        
        redundant_relationships = []
        total_checked = 0
        
        # Check each relationship for redundancy
        for rel in relationships:
            total_checked += 1
            pred_id = rel.get('pred_task_id', '')
            succ_id = rel.get('succ_task_id', '')
            rel_type = rel.get('pred_type', 'PR_FS')
            direct_lag = safe_float(rel.get('lag_hr_cnt', 0))
            
            if pred_id and succ_id:
                # Check for alternate paths
                if has_alternate_path(graph, pred_id, succ_id, (rel_type, direct_lag)):
                    # Get activity codes for readable output
                    pred_code = next((act.get('task_code', pred_id) for act in activities 
                                    if act.get('task_id', '') == pred_id), pred_id)
                    succ_code = next((act.get('task_code', succ_id) for act in activities 
                                    if act.get('task_id', '') == succ_id), succ_id)
                    
                    redundant_relationships.append({
                        'predecessor_id': pred_id,
                        'successor_id': succ_id,
                        'predecessor_code': pred_code,
                        'successor_code': succ_code,
                        'relationship_type': rel_type,
                        'lag_hours': direct_lag
                    })
        
        return {
            'redundant_relationships': redundant_relationships,
            'total_relationships_checked': total_checked,
            'redundant_count': len(redundant_relationships)
        }
    
    except Exception as e:
        st.error(f"Error in redundant logic analysis: {e}")
        return {
            'redundant_relationships': [],
            'total_relationships_checked': 0,
            'redundant_count': 0
        }

def has_alternate_path(graph, start, end, direct_rel):
    """Check if there's an alternate path between start and end nodes."""
    direct_type, direct_lag = direct_rel
    
    # Use BFS to find alternate paths
    queue = deque([(start, 0, [])])  # (current_node, cumulative_lag, path)
    visited = set()
    max_depth = 10  # Prevent infinite loops
    
    while queue and len(visited) < 1000:  # Limit iterations
        current, cumulative_lag, path = queue.popleft()
        
        if len(path) > max_depth:
            continue
            
        if current == end and len(path) > 1:  # Found alternate path
            return True
            
        if current in visited:
            continue
            
        visited.add(current)
        
        # Explore neighbors
        for neighbor, rel_type, lag in graph.get(current, []):
            if neighbor not in path:  # Avoid cycles
                new_path = path + [current]
                queue.append((neighbor, cumulative_lag + lag, new_path))
    
    return False

def parse_file_content(content, filename):
    """Parse XER or XML file content and return structured data."""
    try:
        if filename.lower().endswith('.xer'):
            return parse_xer_simplified(content)
        elif filename.lower().endswith('.xml'):
            return parse_xml_simplified(content)
        else:
            st.error(f"Unsupported file type: {filename}")
            return None
    except Exception as e:
        st.error(f"Error parsing {filename}: {e}")
        return None

def parse_xer_simplified(content):
    """Complete XER parser adapted from original Schedulean.py."""
    lines = content.splitlines()
    tasks, preds, assigns, resources, roles, role_rates = [], [], [], [], [], []
    current, cols = None, []

    for raw in lines:
        line = raw.strip()
        if not line: continue
        if line.startswith('%T'):
            current = line.split('\t')[1]
            cols = []
        elif line.startswith('%F'):
            cols = line.split('\t')[1:]
        elif line.startswith('%R') and current and cols:
            values = line.split('\t')[1:]
            row = {cols[i]: values[i] if i < len(values) else '' for i in range(len(cols))}
            if current == 'TASK': tasks.append(row)
            elif current == 'TASKPRED': preds.append(row)
            elif current == 'TASKRSRC': assigns.append(row)
            elif current == 'RSRC': resources.append(row)
            elif current == 'ROLES': roles.append(row)
            elif current == 'ROLERATE': role_rates.append(row)
    
    return {
        'activities': tasks,
        'relationships': preds,
        'assignments': assigns,
        'resources': resources,
        'roles': roles,
        'role_rates': role_rates,
        'filename': 'XER File'
    }

def parse_xml_simplified(content):
    """Simplified XML parser - would need full implementation."""
    # This is a placeholder - you'd need to implement the full XML parsing
    st.warning("XML parsing not fully implemented in this demo version")
    return {
        'activities': [],
        'relationships': [],
        'assignments': [],
        'resources': [],
        'filename': 'XML File'
    }

def analyze_project_data(data):
    """Analyze parsed project data and return metrics."""
    activities = data['activities']
    relationships = data['relationships']
    assignments = data['assignments']
    resources = data['resources']
    
    # Activity type analysis using proper mapping
    activity_counts = {v: 0 for v in XER_ACTIVITY_MAP.values()}
    for activity in activities:
        task_type = activity.get('task_type', '')
        name = XER_ACTIVITY_MAP.get(task_type)
        if name:
            activity_counts[name] += 1
    
    # Relationship type analysis using proper mapping
    relationship_counts = {v: 0 for v in XER_REL_MAP.values()}
    for rel in relationships:
        rel_type = rel.get('pred_type', 'PR_FS')
        name = XER_REL_MAP.get(rel_type)
        if name:
            relationship_counts[name] += 1
    
    # Resource assignment analysis
    resource_counts = defaultdict(int)
    total_assignments = len(assignments)
    
    # Create resource lookup
    resource_lookup = {r.get('rsrc_id', ''): r for r in resources}
    
    for assignment in assignments:
        rsrc_id = assignment.get('rsrc_id', '')
        resource = resource_lookup.get(rsrc_id, {})
        rsrc_type = resource.get('rsrc_type', '')
        
        if rsrc_type == 'RT_Labor':
            resource_counts['Labor'] += 1
        elif rsrc_type == 'RT_Mat':
            resource_counts['Material'] += 1
        else:
            resource_counts['Non-Labor'] += 1
    
    # Cost analysis
    labor_cost = sum(safe_float(a.get('target_cost', 0)) for a in assignments 
                    if resource_lookup.get(a.get('rsrc_id', ''), {}).get('rsrc_type') == 'RT_Labor')
    nonlabor_cost = sum(safe_float(a.get('target_cost', 0)) for a in assignments 
                       if resource_lookup.get(a.get('rsrc_id', ''), {}).get('rsrc_type') not in ['RT_Labor', 'RT_Mat'])
    material_cost = sum(safe_float(a.get('target_cost', 0)) for a in assignments 
                       if resource_lookup.get(a.get('rsrc_id', ''), {}).get('rsrc_type') == 'RT_Mat')
    
    # Redundant logic analysis
    redundant_logic = analyze_redundant_logic(activities, relationships)
    
    return {
        'activity_counts': dict(activity_counts),
        'relationship_counts': dict(relationship_counts),
        'resource_counts': dict(resource_counts),
        'total_assignments': total_assignments,
        'total_resources': len(resources),
        'costs': {
            'labor': labor_cost,
            'nonlabor': nonlabor_cost,
            'material': material_cost
        },
        'redundant_logic': redundant_logic
    }

# Streamlit App
def main():
    st.set_page_config(
        page_title="Schedulean - P6 Schedule Analyzer",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Schedulean - P6 Schedule Analyzer")
    st.markdown("*Cloud-based Primavera P6 schedule analysis tool*")
    
    # Sidebar for file upload
    st.sidebar.header("📁 Upload P6 Files")
    uploaded_files = st.sidebar.file_uploader(
        "Choose XER or XML files",
        type=['xer', 'xml'],
        accept_multiple_files=True,
        help="Upload one or more Primavera P6 XER or XML export files"
    )
    
    if not uploaded_files:
        st.info("👆 Please upload one or more P6 files using the sidebar to begin analysis")
        
        # Show sample data or instructions
        st.markdown("""
        ### 🚀 Getting Started
        
        1. **Upload Files**: Use the file uploader in the sidebar to select your P6 XER or XML files
        2. **View Analysis**: Switch between Analysis and Cost Metrics tabs to explore your data
        3. **Export Data**: Download results as CSV files for further analysis
        
        ### 📋 Supported Features
        
        - **Activity Analysis**: Count activities by type (WBS Summary, Resource Dependent, etc.)
        - **Relationship Analysis**: Count relationships by type (FS, FF, SS, SF)
        - **Resource Analysis**: Analyze resource assignments by type
        - **Cost Metrics**: Break down costs by Labor, Non-Labor, and Material
        - **Redundant Logic**: Identify unnecessary relationships in your schedule
        - **Multi-file Support**: Analyze multiple projects simultaneously
        """)
        return
    
    # Process uploaded files
    all_results = []
    
    with st.spinner("🔄 Processing files..."):
        for uploaded_file in uploaded_files:
            try:
                # Read file content
                content = uploaded_file.read().decode('utf-8', errors='ignore')
                
                # Parse the file
                data = parse_file_content(content, uploaded_file.name)
                
                if data:
                    # Analyze the data
                    results = analyze_project_data(data)
                    results['filename'] = uploaded_file.name
                    all_results.append(results)
                    
            except Exception as e:
                st.error(f"Error processing {uploaded_file.name}: {e}")
    
    if not all_results:
        st.error("No files were successfully processed. Please check your file formats.")
        return
    
    # Create tabs for different views
    tab1, tab2 = st.tabs(["📈 Analysis", "💰 Cost Metrics"])
    
    with tab1:
        st.header("📈 Schedule Analysis")
        
        # File selector if multiple files
        if len(all_results) > 1:
            selected_file = st.selectbox(
                "Select file to analyze:",
                options=range(len(all_results)),
                format_func=lambda x: all_results[x]['filename']
            )
            results = all_results[selected_file]
        else:
            results = all_results[0]
            st.subheader(f"📄 {results['filename']}")
        
        # Create columns for metrics
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏗️ Activity Types")
            activity_df = pd.DataFrame(
                list(results['activity_counts'].items()),
                columns=['Activity Type', 'Count']
            )
            st.dataframe(activity_df, use_container_width=True)
            
            # Download button for activity data
            csv = activity_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Activity Data",
                data=csv,
                file_name=f"activity_analysis_{results['filename']}.csv",
                mime="text/csv"
            )
            
            st.subheader("🔗 Relationship Types")
            relationship_df = pd.DataFrame(
                list(results['relationship_counts'].items()),
                columns=['Relationship Type', 'Count']
            )
            st.dataframe(relationship_df, use_container_width=True)
            
        with col2:
            st.subheader("👥 Resource Assignments")
            resource_df = pd.DataFrame(
                list(results['resource_counts'].items()),
                columns=['Resource Type', 'Count']
            )
            st.dataframe(resource_df, use_container_width=True)
            
            # Summary metrics
            st.subheader("📊 Summary")
            st.metric("Total Assignments", results['total_assignments'])
            st.metric("Total Resources", results['total_resources'])
            
            # Redundant logic
            redundant_count = results['redundant_logic']['redundant_count']
            st.metric("Redundant Relationships", redundant_count)
            
            if redundant_count > 0:
                with st.expander("🔍 View Redundant Relationships"):
                    redundant_df = pd.DataFrame(results['redundant_logic']['redundant_relationships'])
                    st.dataframe(redundant_df, use_container_width=True)
                    
                    # Download redundant relationships
                    csv = redundant_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Redundant Logic",
                        data=csv,
                        file_name=f"redundant_logic_{results['filename']}.csv",
                        mime="text/csv"
                    )
    
    with tab2:
        st.header("💰 Cost Metrics")
        
        # File selector if multiple files
        if len(all_results) > 1:
            selected_file_costs = st.selectbox(
                "Select file for cost analysis:",
                options=range(len(all_results)),
                format_func=lambda x: all_results[x]['filename'],
                key="cost_file_selector"
            )
            results = all_results[selected_file_costs]
        else:
            results = all_results[0]
        
        costs = results['costs']
        
        # Create cost breakdown
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("💼 Labor Costs")
            st.metric("Total Labor Cost", f"${costs['labor']:,.2f}")
            
        with col2:
            st.subheader("🏗️ Non-Labor Costs")
            st.metric("Total Non-Labor Cost", f"${costs['nonlabor']:,.2f}")
            
        with col3:
            st.subheader("🧱 Material Costs")
            st.metric("Total Material Cost", f"${costs['material']:,.2f}")
        
        # Total cost
        total_cost = costs['labor'] + costs['nonlabor'] + costs['material']
        st.subheader("💰 Total Project Cost")
        st.metric("Total Cost", f"${total_cost:,.2f}")
        
        # Cost breakdown chart
        if total_cost > 0:
            cost_breakdown = pd.DataFrame({
                'Cost Type': ['Labor', 'Non-Labor', 'Material'],
                'Amount': [costs['labor'], costs['nonlabor'], costs['material']],
                'Percentage': [
                    (costs['labor'] / total_cost) * 100,
                    (costs['nonlabor'] / total_cost) * 100,
                    (costs['material'] / total_cost) * 100
                ]
            })
            
            st.subheader("📊 Cost Distribution")
            st.bar_chart(cost_breakdown.set_index('Cost Type')['Amount'])
            
            # Cost breakdown table
            st.subheader("📋 Detailed Cost Breakdown")
            st.dataframe(cost_breakdown, use_container_width=True)
            
            # Download cost data
            csv = cost_breakdown.to_csv(index=False)
            st.download_button(
                label="📥 Download Cost Analysis",
                data=csv,
                file_name=f"cost_analysis_{results['filename']}.csv",
                mime="text/csv"
            )
    
    # Comparison view if multiple files
    if len(all_results) > 1:
        st.header("🔄 Multi-File Comparison")
        
        # Create comparison dataframes
        comparison_data = []
        for result in all_results:
            row = {
                'File': result['filename'],
                'Total Activities': sum(result['activity_counts'].values()),
                'Total Relationships': sum(result['relationship_counts'].values()),
                'Total Assignments': result['total_assignments'],
                'Total Resources': result['total_resources'],
                'Labor Cost': result['costs']['labor'],
                'Non-Labor Cost': result['costs']['nonlabor'],
                'Material Cost': result['costs']['material'],
                'Total Cost': result['costs']['labor'] + result['costs']['nonlabor'] + result['costs']['material'],
                'Redundant Relations': result['redundant_logic']['redundant_count']
            }
            comparison_data.append(row)
        
        comparison_df = pd.DataFrame(comparison_data)
        st.dataframe(comparison_df, use_container_width=True)
        
        # Download comparison
        csv = comparison_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Comparison",
            data=csv,
            file_name="multi_file_comparison.csv",
            mime="text/csv"
        )

if __name__ == "__main__":
    main()
