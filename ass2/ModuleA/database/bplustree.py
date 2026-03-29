import bisect
import graphviz

class BPlusTreeNode:
    def __init__(self, order, is_leaf=False):
        self.order = order
        self.is_leaf = is_leaf
        self.keys = []
        self.children = []
        self.values = []  # Separate array for leaf nodes values
        self.next = None

    def is_full(self):
        return len(self.keys) == self.order - 1

class BPlusTree:
    def __init__(self, order=8):
        self.order = order
        self.root = BPlusTreeNode(order, is_leaf=True)

    def search(self, key):
        node = self.root
        while not node.is_leaf:
            i = bisect.bisect_right(node.keys, key)
            node = node.children[i]
        
        i = bisect.bisect_left(node.keys, key)
        if i < len(node.keys) and node.keys[i] == key:
            return node.values[i]
        return None

    def insert(self, key, value):
        root = self.root
        if root.is_full():
            new_root = BPlusTreeNode(self.order, is_leaf=False)
            self.root = new_root
            new_root.children.append(root)
            self._split_child(new_root, 0)
            self._insert_non_full(new_root, key, value)
        else:
            self._insert_non_full(root, key, value)

    def _insert_non_full(self, node, key, value):
        if node.is_leaf:
            i = bisect.bisect_left(node.keys, key)
            if i < len(node.keys) and node.keys[i] == key:
                node.values[i] = value
            else:
                node.keys.insert(i, key)
                node.values.insert(i, value)
        else:
            i = bisect.bisect_right(node.keys, key)
            if node.children[i].is_full():
                self._split_child(node, i)
                if key > node.keys[i]:
                    i += 1
            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent, index):
        order = self.order
        node = parent.children[index]
        new_node = BPlusTreeNode(order, is_leaf=node.is_leaf)
        
        if node.is_leaf:
            mid = len(node.keys) // 2
            new_node.keys = node.keys[mid:]
            new_node.values = node.values[mid:]
            node.keys = node.keys[:mid]
            node.values = node.values[:mid]
            
            new_node.next = node.next
            node.next = new_node
            
            parent.keys.insert(index, new_node.keys[0])
            parent.children.insert(index + 1, new_node)
        else:
            mid = len(node.keys) // 2
            new_node.keys = node.keys[mid+1:]
            new_node.children = node.children[mid+1:]
            up_key = node.keys[mid]
            node.keys = node.keys[:mid]
            node.children = node.children[:mid+1]
            
            parent.keys.insert(index, up_key)
            parent.children.insert(index + 1, new_node)

    def delete(self, key):
        if not self.root.keys:
            return False
            
        deleted = self._delete(self.root, key)
        
        if not self.root.keys and not self.root.is_leaf:
            self.root = self.root.children[0]
            
        return deleted

    def _delete(self, node, key):
        min_keys = (self.order // 2) - 1 if self.order % 2 == 0 else self.order // 2

        if node.is_leaf:
            i = bisect.bisect_left(node.keys, key)
            if i < len(node.keys) and node.keys[i] == key:
                node.keys.pop(i)
                node.values.pop(i)
                return True
            return False
        else:
            i = bisect.bisect_right(node.keys, key)
            deleted = self._delete(node.children[i], key)
            
            if deleted:
                if len(node.children[i].keys) < min_keys:
                    self._fill_child(node, i)
                    
            return deleted

    def _fill_child(self, node, index):
        min_keys = (self.order // 2) - 1 if self.order % 2 == 0 else self.order // 2
        
        if index > 0 and len(node.children[index - 1].keys) > min_keys:
            self._borrow_from_prev(node, index)
        elif index < len(node.children) - 1 and len(node.children[index + 1].keys) > min_keys:
            self._borrow_from_next(node, index)
        else:
            if index < len(node.children) - 1:
                self._merge(node, index)
            else:
                self._merge(node, index - 1)

    def _borrow_from_prev(self, node, index):
        child = node.children[index]
        sibling = node.children[index - 1]
        
        if child.is_leaf:
            child.keys.insert(0, sibling.keys.pop(-1))
            child.values.insert(0, sibling.values.pop(-1))
            node.keys[index - 1] = child.keys[0]
        else:
            child.keys.insert(0, node.keys[index - 1])
            node.keys[index - 1] = sibling.keys.pop(-1)
            child.children.insert(0, sibling.children.pop(-1))

    def _borrow_from_next(self, node, index):
        child = node.children[index]
        sibling = node.children[index + 1]
        
        if child.is_leaf:
            child.keys.append(sibling.keys.pop(0))
            child.values.append(sibling.values.pop(0))
            node.keys[index] = sibling.keys[0]
        else:
            child.keys.append(node.keys[index])
            node.keys[index] = sibling.keys.pop(0)
            child.children.append(sibling.children.pop(0))

    def _merge(self, node, index):
        child = node.children[index]
        sibling = node.children[index + 1]
        
        if child.is_leaf:
            child.keys.extend(sibling.keys)
            child.values.extend(sibling.values)
            child.next = sibling.next
            node.keys.pop(index)
            node.children.pop(index + 1)
        else:
            child.keys.append(node.keys.pop(index))
            child.keys.extend(sibling.keys)
            child.children.extend(sibling.children)
            node.children.pop(index + 1)

    def update(self, key, new_value):
        node = self.root
        while not node.is_leaf:
            i = bisect.bisect_right(node.keys, key)
            node = node.children[i]
        
        i = bisect.bisect_left(node.keys, key)
        if i < len(node.keys) and node.keys[i] == key:
            node.values[i] = new_value
            return True
        return False

    def range_query(self, start_key, end_key):
        node = self.root
        while not node.is_leaf:
            i = bisect.bisect_right(node.keys, start_key)
            node = node.children[i]
            
        results = []
        while node:
            for k, v in zip(node.keys, node.values):
                if start_key <= k <= end_key:
                    results.append((k, v))
                elif k > end_key:
                    return results
            node = node.next
        return results

    def get_all(self):
        node = self.root
        while not node.is_leaf:
            node = node.children[0]
            
        results = []
        while node:
            for k, v in zip(node.keys, node.values):
                results.append((k, v))
            node = node.next
        return results

    def visualize_tree(self):
        dot = graphviz.Digraph(comment='B+ Tree')
        dot.attr(rankdir='TB', nodesep='0.5', ranksep='1.0')
        if not self.root.keys:
            return dot
        self._add_nodes(dot, self.root)
        self._add_edges(dot, self.root)
        
        node = self.root
        while not node.is_leaf:
            if not node.children: break
            node = node.children[0]
            
        prev_name = None
        while node:
            node_name = str(id(node))
            if prev_name:
                dot.edge(f"{prev_name}:next", node_name, constraint='false', style='dashed', color='blue', penwidth='2.0', label='next')
            prev_name = node_name
            node = node.next
            
        return dot

    def _add_nodes(self, dot, node):
        node_name = str(id(node))
        
        if node.is_leaf:
            # Leaf node representation
            # Row 1: Keys
            # Row 2: Values (truncated if too long)
            # Add a 'next' port at the end
            html_parts = ['<<table border="0" cellborder="1" cellspacing="0" bgcolor="#e6ffe6"><tr>']
            for i, k in enumerate(node.keys):
                html_parts.append(f'<td port="k{i}"><b>{str(k)}</b></td>')
            html_parts.append('<td port="next" rowspan="2" bgcolor="#ccffcc"><i>next</i></td>')
            html_parts.append('</tr><tr>')
            for i, v in enumerate(node.values):
                val_str = str(v)
                if len(val_str) > 10: val_str = val_str[:10] + '...'
                html_parts.append(f'<td>{val_str}</td>')
            html_parts.append('</tr></table>>')
            dot.node(node_name, label="".join(html_parts), shape='none', margin='0')
        else:
            # Internal node representation
            html_parts = ['<<table border="0" cellborder="1" cellspacing="0" bgcolor="#e6f2ff"><tr>']
            for i, k in enumerate(node.keys):
                html_parts.append(f'<td port="p{i}" bgcolor="#cce6ff">&bull;</td>')
                html_parts.append(f'<td><b>{str(k)}</b></td>')
            html_parts.append(f'<td port="p{len(node.keys)}" bgcolor="#cce6ff">&bull;</td>')
            html_parts.append('</tr></table>>')
            dot.node(node_name, label="".join(html_parts), shape='none', margin='0')
            
            for child in node.children:
                self._add_nodes(dot, child)

    def _add_edges(self, dot, node):
        if not node.is_leaf:
            node_name = str(id(node))
            for i, child in enumerate(node.children):
                child_name = str(id(child))
                dot.edge(f'{node_name}:p{i}', child_name)
                self._add_edges(dot, child)
