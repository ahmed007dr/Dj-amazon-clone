
// for preloader none when complete load
window.addEventListener("load", function(){
    var preload = document.querySelector(".preloader");
    preload.classList.add("finish__load");
});


// FOR NAVBAR FIXED
$(window).on("scroll", function(){
    var scrolling = $(this).scrollTop();
    if (scrolling > 130){
        $(".navbar").addClass("navbar-fixed");
    }else{
        $(".navbar").removeClass("navbar-fixed");
    }
});

//for menu hover active when click
$(".nav-item").on("click", function(){
    $("li.nav-item").removeClass("active");
    $(this).addClass("active");
});


//FOR DOCUMENTATION QUESTION BAR FIXED
$(window).on("scroll", function(){
    var scrolling = $(this).scrollTop();
    if (scrolling > 450){
        $(".doc-que").addClass("doc-active");
    }else{
        $(".doc-que").removeClass("doc-active");
    }
});












