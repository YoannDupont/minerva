//==============================================================================
// functions
//==============================================================================


function jointext(back_to_text, name) {
    return "<p>"
        + back_to_text[name].map(item => item.text).join("</p><p>")
        + "</p>"
    ;
}


function jointextsource(back_to_text, name) {
    return "<p>"
        + back_to_text[name].map(item => "<pre>"+item.source+"</pre>" + item.text).join("</p><p>")
        + "</p>"
    ;
}


function jointextsourcetable(back_to_text, name) {
    return '<table id="sourcetext" style="width:100%">'
        + "<tr><th>source</th><th>text</th></tr>"
        + "<tr>"
        + back_to_text[name].map(item => "<td>"+item.source+"</td>" + "<td>"+item.text+"</td>").join("</tr><tr>")
        + "</tr>"
        + "</table>"
    ;
}


function xyShift(scale) {
    return {"x": scale * (2 * Math.random() - 1), "y": scale * (2 * Math.random() - 1)};
}


function adjustNodes(d) {
    let padding = [];

    if (d[1].length < 3) {
        let coord_shift = xyShift(0.01);
        let x_shift = coord_shift.x;
        let y_shift = coord_shift.y;
        padding = [
            [d[1][0].x + x_shift, d[1][0].y + y_shift],
            [d[1][0].x - x_shift, d[1][0].y + y_shift],
        ];
    }

    return d[1].map(function(d) { return [d.x, d.y]; }).concat(padding);
}


function nodeArrayToHull(d) {
    return "M" + d3.polygonHull(adjustNodes(d)).join("L") + "Z";
}


function groupColor(grp) {
    if (grp.toLowerCase().includes("negati")) {
        return color_OM(0.1);
    } else if (grp.toLowerCase().includes("positi")) {
        return color_OM(0.9);
    }
    // this way to scale is better when trying to remove edge colors
    let scale = 1 / (groups.length * 1.15);
    return color(scale * (groups.indexOf(grp)) + 0.15);
}


function normalizeLinkStrength(strength) {
    return (strength - link_min_strength) / link_max_strength;
}


function scaleLinkStrength(strength) {
    const scale = 10;
    return Math.max(scale * normalizeLinkStrength(strength), 1);
}


function linkColor(strength) {
    return color_link(1 - normalizeLinkStrength(strength));
}


function onTick() {
    // zoom in/out makes node placement not a problem
    node
        .attr("cx", function(d) { return d.x; })
        .attr("cy", function(d) { return d.y; })
    ;

    link
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; })
    ;

    hull
        .data(node_groups)
        .attr("d", function(d) { return nodeArrayToHull(d); })
        .enter()  // #TODO use join instead to auto-exit? Might be useful when collapsing nodes
        .append("path", "circle")
        .attr("class", 'hull')
    ;

    entity_node
        .attr("x", function(d) { return d.x; })
        .attr("y", function(d) { return d.y - 16; })
    ;
}


function onDragStart(event) {
    if (!event.active) simulation.alphaTarget(0.7).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
}
function onDrag(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
}
function onDragEnd(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
}


function zoomTransform(event) {
    hull.attr("transform", event.transform);
    link.attr("transform", event.transform);
    node.attr("transform", event.transform);
    entity_node.attr("transform", event.transform);
    d3.select("#textnodetmp").attr("transform", event.transform);
}


function makeGraph(graph_data) {
    node_groups = d3.group(graph_data.nodes, d => d.group);

    groups = [];
    for (let i = 0; i < graph_data.nodes.length; i++) {
        if (! groups.includes(graph_data.nodes[i].group)) {
            groups.push(graph_data.nodes[i].group);
        }
    }

    link_min_strength = Number.MAX_SAFE_INTEGER;
    link_max_strength = 1;
    for (let i = 0; i < graph_data.links.length; i++) {
        link_min_strength = Math.min(link_min_strength, graph_data.links[i].value);
        link_max_strength = Math.max(link_max_strength, graph_data.links[i].value);
    }

    graph = graph_data;

    update();
}


function nodeClass(nd) {
    // return d.class ?? "node";
    return nd.class ?? nd.group != "opinion mining" ? "entity" : "node";
}


function update() {
    // TODO: use join instead of enter/exit/merge.

    hull = hull.data(node_groups);
    hull.exit().remove(); // does not seem to do anything currently
    let hull_update = hull
        .enter()  // use join instead to auto-exit? Might be useful when collapsing nodes
        .append("path", "circle")
            .attr("class", 'hull')
            .style("fill", function(d) { return groupColor(d[0]); }) // .group() gives array[key, value] <=> key
            .style("stroke", function(d) { return groupColor(d[0]); })
        .on("click", function(event, d) {
            let mynodes = graph_data.data.nodes.filter(item => item.group == d[0]).map(item => item.id);  // .group() gives array[key, value] <=> key. TODO: change to better accomodate mentions
            mynodes = mynodes.map(item => "<h3>"+item+"</h3>" + jointextsourcetable(graph_data.back_to_text, item));
            let imageurl = graph_data.name2image[d[0]];
            imageurl = imageurl ? imageurl : DEFAULT_IMAGE;
            document.getElementById("backtotext").innerHTML = 
                "<h2>" + d[0] + "</h2>"
                + mynodes.join("")
            ;
            document.getElementById("image").innerHTML =
                "<img src=\""
                + imageurl
                + "\" width=\"200px\" height=\"282px\" />"
            ;
        })
        .on("mouseover", function(event, d) {
            const pointer = d3.pointer(event);
            const x = pointer[0];
            const y = pointer[1];
            svg.append("text")
                .attr("id", "texthulltmp")
                .attr("x", x - d[0].length)
                .attr("y", y - 5)
                .text(d[0])
                    .style("font-family", "Arial")
                    .style("font-size", 16)
            ;
        })
        .on("mouseout", function(event, d) {
            d3.select("#texthulltmp").remove();
        })
    ;
    //~ hull_update.append("title").text(function(d) { return d[0]; } );
    hull = hull.merge(hull_update);

    node = node.data(graph.nodes, function(d) { return d.id; });
    node.exit().remove();
    let node_update = node.enter().append("circle")
        .attr("class", function (d) { return nodeClass(d); })
        .attr("fill", function(d) { return groupColor(d.group); })
        .call(d3.drag()
            .on("start", onDragStart)
            .on("drag", onDrag)
            .on("end", onDragEnd)
        )
        .on("click", function(event, d) {
            let imageurl = graph_data.name2image[d.group];
            imageurl = imageurl ? imageurl : DEFAULT_IMAGE;
            document.getElementById("backtotext").innerHTML =
                "<h2>" + d.id + "</h2>"
                + jointextsourcetable(graph_data.back_to_text, d.id)  // TODO: change to better accomodate mentions
            ;
            document.getElementById("image").innerHTML =
                "<img src=\""
                + imageurl
                + "\" width=\"200px\" height=\"282px\" />"
            ;
        })
        .on("mouseover", function(event, d) {
            if (d.class != "entity") {
                svg.append("text")
                    .attr("id", "textnodetmp")
                    .attr("x", d.x)
                    .attr("y", d.y - 10)
                    .text(d.label ?? d.name)
                        .style("font-family", "Arial")
                        .style("font-size", 12)
                ;
            }
        })
        .on("mouseout", function(event, d) {
            d3.select("#textnodetmp").remove();
        })
    ;
    node_update.append("title").text(function(d) { return (d.label ?? d.id); });
    node = node.merge(node_update);

    entity_node = entity_node.data(graph.nodes.filter(nd => nd.class === "entity"), function(d) { return d.id; });
    entity_node.exit().remove();
    let entity_node_update = entity_node.enter().append("text")
        .text(function (d) { return d.id; })
        .style("text-anchor", "middle")
        .style("font-family", "Arial")
        .style("font-size", 12)
    ;
    entity_node = entity_node.merge(entity_node_update);

    link = link.data(graph.links, function(d) { return d.id; });
    link.exit().remove();
    let link_update = link.enter().append("line")
        .attr("class", "link")
        .style("stroke", function(d) { return linkColor(d.value); })
        .style("stroke-width", function(d) { return scaleLinkStrength(d.value || 1); })
    ;
    //~ link_update.append("title").text(function(d) { return d.value; });
    link = link.merge(link_update);

    simulation
        .nodes(graph.nodes)
        .on("tick", onTick);

    simulation.force("link")
        .links(graph.links);

    simulation.alpha(1.0).alphaTarget(0.0).restart();
}


//==============================================================================
// graph initialization
//==============================================================================


var graph_data;
var graph, node_groups;
var link_min_strength = Number.MAX_SAFE_INTEGER, link_max_strength = 1;

var groups = [];
const color = d3.interpolateTurbo;
const color_OM = d3.interpolateRdYlGn;
const color_link = d3.interpolateRdYlBu;

const DEFAULT_IMAGE = "https://upload.wikimedia.org/wikipedia/commons/a/ac/No_image_available.svg";

const graph_div = document.getElementById("graph");
const width = document.getElementById("graph").offsetWidth;  // svg width
const height = document.getElementById("graph").offsetHeight; // svg height

var svg = d3.select(graph_div).append("svg")
    .attr("width", width)
    .attr("height", height);

var hull = svg.append("g").selectAll(".path");
var link = svg.append("g").selectAll(".line");
var node = svg.append("g").selectAll(".node");
var entity_node = svg.append("g").selectAll(".entity");

var simulation = d3.forceSimulation()
    .force("link", d3.forceLink().id(function(d) { return d.id; }).strength(0.2))
    .force("charge", d3.forceManyBody().strength(function(d) { return -100; }))
    .force("center", d3.forceCenter(width / 2, height / 2))
;

var zoom_handler = d3.zoom().on("zoom", zoomTransform);

zoom_handler(svg);

window.init = function init(source_data) {
    if (simulation) {
        hull.exit().remove();
        link.exit().remove();
        node.exit().remove();
        entity_node.exit().remove();
        simulation.stop();
    }

    graph_data = source_data;
    makeGraph(source_data.data);
}
