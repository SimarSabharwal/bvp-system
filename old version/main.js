// ================================
// BVP ERP SYSTEM
// main.js
// ================================

// Auto Refresh Every Minute
setInterval(function () {
    if (
        window.location.pathname.includes("dashboard")
    ) {
        location.reload();
    }
}, 60000);


// Live Clock
function updateClock() {

    const clock = document.getElementById("liveClock");

    if (!clock) return;

    const now = new Date();

    clock.innerHTML = now.toLocaleTimeString();

}

setInterval(updateClock, 1000);

window.onload = updateClock;


// Smooth Scroll
document.querySelectorAll("a").forEach(anchor => {

    anchor.addEventListener("click", function (e) {

        const href = this.getAttribute("href");

        if (href.startsWith("#")) {

            e.preventDefault();

            document.querySelector(href).scrollIntoView({

                behavior: "smooth"

            });

        }

    });

});


// Highlight Current Row

window.onload = function(){

    updateClock();

    let rows=document.querySelectorAll("tbody tr");

    rows.forEach(r=>{

        if(r.innerText.includes("BREAK")){

            r.style.background="#fff9c4";

        }

    });

};


// Card Hover Animation

let cards=document.querySelectorAll(".card");

cards.forEach(card=>{

    card.addEventListener("mouseenter",()=>{

        card.style.transform="translateY(-8px)";

    });

    card.addEventListener("mouseleave",()=>{

        card.style.transform="translateY(0px)";

    });

});


// Disable Right Click (Optional)

document.addEventListener("contextmenu",function(e){

    e.preventDefault();

});


// Prevent Form Resubmit

if(window.history.replaceState){

    window.history.replaceState(null,null,window.location.href);

}