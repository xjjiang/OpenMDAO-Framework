
import logging

from enthought.traits.api import implements
import networkx as nx
from networkx.algorithms.traversal import is_directed_acyclic_graph, strongly_connected_components

from openmdao.main.interfaces import IAssembly, IComponent
from openmdao.main.workflow import Workflow
from openmdao.main.drivertree import DriverForest, create_labeled_graph

__all__ = ['Dataflow']

                
class Dataflow(Workflow):
    """
    A Dataflow consists of a collection of Components which are executed in 
    data flow order.
    """

    def __init__(self, name, parent=None):
        """ Create an empty flow. """
        super(Dataflow, self).__init__(name, parent, add_to_parent=False)
        self._no_ref_graph = nx.DiGraph()
        
    def execute(self):
        try:
            super(Dataflow, self).execute()
        finally:
            self._drvsorter = None
            
    def has_node(self, name):
        return name in self._no_ref_graph
        
    def add_node(self, name):
        self._no_ref_graph.add_node(name)
        
    def remove_node(self, name):
        self._no_ref_graph.remove_node(name)
        
    def get_graph(self):
        return self._no_ref_graph
        
    def connect(self, srccompname, destcompname, srcvarname, destvarname):
        # if an edge already exists between the two components, just increment the ref count
        graph = self._no_ref_graph
        try:
            graph[srccompname][destcompname] += 1
        except KeyError:
            graph.add_edge(srccompname, destcompname, data=1)
            
        if not is_directed_acyclic_graph(graph):
            # do a little extra work here to give more info to the user in the error message
            strongly_connected = strongly_connected_components(graph)
            refcount = graph[srccompname][destcompname] - 1
            if refcount == 0:
                graph.remove_edge(srccompname, destcompname)
            else:
                graph[srccompname][destcompname] = refcount
            for strcon in strongly_connected:
                if len(strcon) > 1:
                    self.raise_exception(
                        'circular dependency (%s) would be created by connecting %s to %s' %
                                 (str(strcon), 
                                  '.'.join([srccompname,srcvarname]), 
                                  '.'.join([destcompname,destvarname])), RuntimeError) 
        
    def disconnect(self, comp1name, comp2name):
        """Decrement the ref count for the edge in the dependency graph 
        between the two components, or remove the edge if the ref count
        reaches 0.
        """
        refcount = self._no_ref_graph[comp1name][comp2name] - 1
        if refcount == 0:
            self._no_ref_graph.remove_edge(comp1name, comp2name)
        else:
            self._no_ref_graph[comp1name][comp2name] = refcount

            
    def _find_drivers(self, names):
        """Returns a list of Drivers found in the given list of names."""
        driverset = set([obj.name for obj in self.parent.drivers])
        return [getattr(self.parent, n) for n in names if n in driverset]
        
    def nodes_iter(self):
        """Iterate through the nodes in dataflow order, allowing for multiple Driver
        loops within the same Assembly.
        """
        drivers = self.parent.drivers
        self._drvsorter = None
        
        if len(drivers) == 0:  # no driver, so just sort and go
            for n in nx.topological_sort(self._no_ref_graph):
                yield getattr(self.parent, n)
        elif len(drivers) == 1:  # one driver, so add its output ref edges, sort and go
            graph = self._no_ref_graph.copy()
            graph.add_edges_from(drivers[0].get_ref_graph(iostatus='out').edges_iter())
            for n in nx.topological_sort(graph):
                yield getattr(self.parent, n)
            return
        else:  # multiple drivers
            graph = self._no_ref_graph.copy()
            
            # add all ReferenceVariable edges from all drivers to the graph 
            # (which will likely create one or more loops)
            for drv in drivers:
                graph.add_edges_from(drv.get_ref_graph().edges_iter())

            # each loop is a strongly connected component (SCC)
            # NOTE: for nested drivers, multiple drivers will exist within
            # the same SCC, and that SCC will have to be subdivided into sub SCCs
            strongs = strongly_connected_components(graph)
            
            if len(strongs) > 0 and len(strongs[0]) == 1:
                # no loops found (SCCs are returned largest to smallest), 
                # so just sort and we're done. 
                for compname in nx.topological_sort(graph):
                    yield getattr(self.parent, compname)
                return
            
            # we have at least one loop, so...
            # create a new graph with SCCs collapsed down into
            # nodes so that we can make the graph topologically sortable
            strong_dict = {}
            strong_graph = nx.DiGraph()
            for i,strong in enumerate(strongs):
                strong_graph.add_node(i)
                for node in strong:
                    strong_dict[node] = i # map nodes to their strongly connected comp
            for node in graph.nodes():
                for u,v in graph.edges_iter(node):
                    if strong_dict[u] != strong_dict[v]:
                        strong_graph.add_edge(strong_dict[u], strong_dict[v])
            sorted_strongs = nx.topological_sort(strong_graph)
            
            for sccomp in sorted_strongs:
                if len(strongs[sccomp]) == 1:  # no loop, just a single component
                    yield getattr(self.parent, strongs[sccomp][0])
                else:  # some kind of loop
                    for comp in self._loop_iter(strongs[sccomp]):
                        yield comp
                    
    def _loop_iter(self, loopcomps):
        """Return components within the given loop in dataflow order."""
        drivers = self._find_drivers(loopcomps) # find drivers in this loop
        if len(drivers) == 1:  # only one driver in this loop. so just tell it to run
                               # and it will run everything else
            yield drivers[0]
        else:   # nested drivers
            subgraph = self._no_ref_graph.subgraph(nbunch=loopcomps) # this has no StringRef edges
            self._drvsorter = DriverForest(drivers)
            collapsed_graph = self._drvsorter.collapse_graph(subgraph)
            for compname in nx.topological_sort(collapsed_graph):
                yield getattr(self.parent, compname)
